"""
SignalRankAI Web API + Paystack Webhook Handler.

Endpoints:
- /signals/{user_id} → User-specific signal feed (API key auth)
- /paystack/webhook → Payment verification + subscription sync
- /metrics → Health + performance metrics (admin only)
- /health → Simple liveness probe

Security:
- API key auth (per-user tokens from db.api_tokens)
- Rate limiting (10 req/min per IP)
- Paystack signature verification
- CORS protection
"""
import asyncio
import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import hmac
import json

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from db.session import get_session
from db.repository import (
    get_api_token_owner,
    count_active_subscriptions,
    paystack_event_identity,
    mark_webhook_event_processed,
)
from db.models import ApiToken, User, Signal
from sqlalchemy import select
from core.redis_state import state
from core.redis_cache import cache_stats
from core.tier_constants import TIER_SCORE_THRESHOLDS
from signalrank_telegram.utils import tier_rank, _effective_tier
from payments.paystack import process_event as process_paystack_event

logger = logging.getLogger(__name__)

app = FastAPI(title="SignalRankAI API", version="1.0.0")

# CORS for Telegram web apps (future)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://t.me", "https://telegram.org"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

class SignalRequest(BaseModel):
    limit: int = 20
    active_only: bool = True
    tier_filter: Optional[str] = None

class HealthResponse(BaseModel):
    status: str = "healthy"
    uptime: float
    signals_active: int
    cache_hit_rate: float

class MetricsResponse(BaseModel):
    cache_stats: Dict[str, float]
    db_connections: int
    signals_generated_1h: int
    signals_delivered_1h: int
    subscriptions_active: int

async def verify_api_key(token: str = Depends(security)) -> int:
    """Verify API token → return user_id or raise 401."""
    raw_token = token.credentials
    if not raw_token:
        raise HTTPException(401, "Missing API key")
    
    try:
        async with get_session() as session:
            user_id = await get_api_token_owner(session, raw_token=raw_token)
            if not user_id:
                raise HTTPException(401, "Invalid or expired API key")
            return int(user_id)
    except Exception:
        raise HTTPException(500, "Token verification failed")

def rate_limit_key(request: Request) -> str:
    """Rate limit key: IP + user-agent fingerprint."""
    client_ip = request.client.host
    user_agent_hash = hashlib.md5(str(request.headers.get("user-agent", "")).encode()).hexdigest()[:8]
    return f"api_rate:{client_ip}:{user_agent_hash}"

async def rate_limit(request: Request, user_id: int):
    """Rate limit: 10 req/min per IP."""
    key = rate_limit_key(request)
    now = time.time()
    
    try:
        pipe = state.pipeline()
        pipe.get(key)
        pipe.incr(key)
        pipe.expire(key, 60)
        hits, _, _ = await state.execute_pipeline(pipe)
        
        if int(hits or 0) > 10:
            raise HTTPException(429, "Rate limit exceeded. Try again in 1 minute.")
    except Exception:
        pass

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Global rate limiting middleware."""
    if request.url.path in ["/health", "/healthz", "/metrics"]:
        response = await call_next(request)
        return response
    
    try:
        await rate_limit(request, user_id=0)  # IP-only for unauth
    except HTTPException:
        raise
    response = await call_next(request)
    return response

@app.get("/health", response_model=HealthResponse)
@app.get("/healthz", response_model=HealthResponse)
async def health():
    """Liveness + readiness probe.
    
    Railway healthcheck - should return quickly even if DB is slow/unavailable.
    Uses a deadline to avoid blocking Railway's healthcheck.
    """
    uptime = time.time() - float(os.getenv("START_TS", str(time.time())))
    
    # Use a deadline to avoid blocking Railway healthcheck
    # If DB is slow/unavailable, still return healthy (status="degraded")
    active_signals = -1
    deadline = time.time() + 3.0  # 3 second deadline
    db_configured = False
    
    # First check if DB is configured
    try:
        from db.session import is_db_configured
        db_configured = is_db_configured()
    except Exception as e:
        logger.warning(f"[healthz] DB config check failed: {e}")
        db_configured = False
    
    if not db_configured:
        logger.warning("[healthz] DB not configured, returning degraded status")
        active_signals = -1
    else:
        try:
            if time.time() >= deadline:
                raise TimeoutError("Health check deadline exceeded")
                
            from sqlalchemy import select
            async with get_session() as session:
                # Check deadline before executing query
                if time.time() >= deadline:
                    raise TimeoutError("Health check deadline exceeded before DB query")
                
                # Try with fallback columns - check if archived/expired exist
                try:
                    count_stmt = select(Signal.signal_id).where(
                        Signal.archived == False,
                        Signal.expired == False
                    )
                    result = await session.execute(count_stmt)
                    active_signals = result.scalar() or 0
                except Exception as col_err:
                    # Fallback: count all signals if columns don't exist
                    logger.warning(f"[healthz] Column check failed, trying fallback: {col_err}")
                    count_stmt = select(Signal.signal_id)
                    result = await session.execute(count_stmt)
                    active_signals = result.scalar() or 0
        except (TimeoutError, asyncio.TimeoutError) as e:
            # DB query took too long - still healthy but degraded
            logger.warning(f"[healthz] DB query timeout: {e}, returning degraded status")
            active_signals = -1
        except Exception as e:
            # DB unavailable or other error - still healthy
            logger.warning(f"[healthz] DB query failed: {e}, returning degraded status")
            active_signals = -1
    
    hit_rate = 0.0
    try:
        cache = await cache_stats()
        hit_rate = float(cache.get("hit_rate", 0))
    except Exception:
        hit_rate = 0.0
    
    return HealthResponse(
        status="healthy" if active_signals >= 0 else "degraded",
        uptime=uptime,
        signals_active=int(active_signals) if active_signals >= 0 else 0,
        cache_hit_rate=hit_rate
    )

@app.get("/metrics", response_model=MetricsResponse)
async def metrics(user_id: int = Depends(verify_api_key)):
    """Admin metrics endpoint."""
    if not await _is_admin_user(user_id):
        raise HTTPException(403, "Admin access required")
    
    cache_stats_data = {}
    try:
        cache_stats_data = await cache_stats()
    except Exception:
        cache_stats_data = {}
    
    subs = 0
    try:
        async with get_session() as session:
            subs = await count_active_subscriptions(session)
    except Exception:
        subs = 0
    
    signals_1h = delivered_1h = 0
    try:
        signals_1h = int(await state.get_sync("metrics:signals_generated_1h") or 0)
        delivered_1h = int(await state.get_sync("metrics:signals_delivered_1h") or 0)
    except Exception:
        signals_1h = delivered_1h = 0
    
    return MetricsResponse(
        cache_stats=cache_stats_data,
        db_connections=len(get_session._pools) if hasattr(get_session, '_pools') else 0,
        signals_generated_1h=signals_1h,
        signals_delivered_1h=delivered_1h,
        subscriptions_active=int(subs)
    )

@app.get("/signals/{user_id}")
async def get_signals(
    user_id: int,
    request: Request,
    req: SignalRequest = Depends(),
    auth_user_id: int = Depends(verify_api_key)
):
    """Get user's active signals (API key auth required)."""
    if auth_user_id != user_id:
        raise HTTPException(403, "Cannot access other user's signals")
    
    await rate_limit(request, user_id)
    
    try:
        async with get_session() as session:
            tier = _effective_tier(user_id)
            base_query = select(Signal).where(
                Signal.archived == False,
                Signal.expired == False
            )
            
            if req.active_only:
                base_query = base_query.where(Signal.created_at >= datetime.utcnow() - timedelta(hours=72))
            
            if tier_rank(tier) < tier_rank("PREMIUM"):
                # Free: recent proof signals only
                base_query = base_query.where(Signal.score >= 80)
            
            signals = (await session.execute(
                base_query.order_by(Signal.created_at.desc()).limit(req.limit)
            )).scalars().all()
            
            signal_list = []
            for sig in signals:
                signal_dict = {
                    "signal_id": sig.signal_id,
                    "asset": sig.asset,
                    "timeframe": sig.timeframe,
                    "direction": sig.direction,
                    "entry": sig.entry,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                    "score": sig.score,
                    "ml_probability": sig.ml_probability,
                    "strategy_name": sig.strategy_name,
                    "created_at": sig.created_at.isoformat() if sig.created_at else None,
                }
                signal_list.append(signal_dict)
            
            return {
                "signals": signal_list,
                "tier": tier,
                "count": len(signal_list),
                "limit": req.limit
            }
            
    except Exception as e:
        logger.error(f"Signals API error user_id={user_id}: {e}")
        raise HTTPException(500, "Failed to fetch signals")

async def _is_admin_user(user_id: int) -> bool:
    """Check if user is admin/owner."""
    from core.settings import OWNER_IDS, ADMIN_IDS
    return user_id in OWNER_IDS or user_id in ADMIN_IDS

def _payments_enabled() -> bool:
    return str(os.getenv("PAYMENTS_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/paystack/webhook")
@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request):
    """Paystack webhook handler (supports both legacy and canonical routes)."""
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        raise HTTPException(400, "Missing Paystack signature")

    secret = (os.getenv("PAYSTACK_WEBHOOK_SECRET") or os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not secret:
        logger.error("PAYSTACK webhook secret not configured")
        raise HTTPException(500, "Webhook configuration error")

    raw_body = await request.body()
    expected_sig = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        logger.warning("Paystack signature mismatch")
        raise HTTPException(401, "Invalid signature")

    try:
        payload: Dict[str, Any] = json.loads((raw_body or b"{}").decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    event = str(payload.get("event") or "").strip()
    data = payload.get("data") or {}
    reference = str(data.get("reference") or "").strip()

    # Best-effort idempotency tracking for duplicate webhook deliveries.
    idempotent = False
    try:
        from db.session import is_db_configured
        if is_db_configured():
            event_id, payload_hash = paystack_event_identity(payload, raw_body)
            async with get_session() as session:
                is_new = await mark_webhook_event_processed(
                    session,
                    provider="paystack",
                    event_id=event_id,
                    event_type=event or "unknown",
                    reference=reference or None,
                    payload_hash=payload_hash,
                    meta={"route": "/webhooks/paystack"},
                )
                await session.commit()
            if not is_new:
                return {"received": True, "verified": False, "idempotent": True, "event": event}
    except Exception as exc:
        logger.warning("Paystack idempotency tracking failed: %s", exc)

    # Support maintenance/test mode without contacting external providers.
    if not _payments_enabled():
        return {"received": True, "verified": False, "idempotent": idempotent, "event": event}

    # Process payment event and trigger auto-upgrade/credits where applicable.
    result = await process_paystack_event(payload)
    verified = bool((result or {}).get("processed"))
    return {
        "received": True,
        "verified": verified,
        "idempotent": idempotent,
        "event": event,
        "result": result or {},
    }

@app.post("/paystack/charge")
async def paystack_charge_create(user_id: int = Depends(verify_api_key)):
    """Create Paystack charge (for manual payments)."""
    # Implementation stub - use client-side Paystack popup instead
    raise HTTPException(501, "Use client-side Paystack integration")


# === Stub scheduler jobs (referenced by railway_main.py) ===
async def _check_waitlist_capacity_job() -> None:
    """Check if VIP seats are available and notify admins.
    
    Stub implementation - VIP waitlist functionality not yet fully implemented.
    Kept here for railway_main.py scheduler compatibility.
    """
    logger.debug("[waitlist] capacity check job ran (stub)")
    pass


async def _monitor_expired_invites_job() -> None:
    """Monitor and process expired VIP invites.
    
    Stub implementation - VIP waitlist functionality not yet fully implemented.
    Kept here for railway_main.py scheduler compatibility.
    """
    logger.debug("[waitlist] expired invites job ran (stub)")
    pass


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
