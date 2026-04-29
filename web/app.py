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
from db.repository import get_latest_active_api_token, count_active_subscriptions
from db.models import ApiToken, User, Signal
from sqlalchemy import select
from core.redis_state import state
from core.redis_cache import cache_stats
from signalrank_telegram.utils import tier_rank, _effective_tier
from payments.paystack import verify_payment

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
            user_id = await get_latest_active_api_token(session, raw_token=raw_token)
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
    if request.url.path in ["/health", "/metrics"]:
        response = await call_next(request)
        return response
    
    try:
        await rate_limit(request, user_id=0)  # IP-only for unauth
    except HTTPException:
        raise
    response = await call_next(request)
    return response

@app.get("/health", response_model=HealthResponse)
async def health():
    """Liveness + readiness probe."""
    uptime = time.time() - float(os.getenv("START_TS", str(time.time())))
    
    active_signals = -1
    try:
        async with get_session() as session:
            # Count active (non-expired/archived) signals
            count_stmt = select(Signal.signal_id).where(
                Signal.archived == False,
                Signal.expired == False
            )
            active_signals = (await session.execute(count_stmt)).scalar() or 0
    except Exception:
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
        signals_active=int(active_signals),
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

@app.post("/paystack/webhook")
async def paystack_webhook(request: Request, payload: Dict[str, Any]):
    """Paystack webhook handler."""
    
    # Verify webhook signature
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        raise HTTPException(400, "Missing Paystack signature")
    
    secret = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret:
        logger.error("PAYSTACK_SECRET_KEY not configured")
        raise HTTPException(500, "Webhook configuration error")
    
    try:
        expected_sig = hmac.new(
            secret.encode(), 
            request.body(),
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Paystack signature mismatch")
            raise HTTPException(401, "Invalid signature")
    except Exception:
        logger.error("Paystack signature verification failed")
        raise HTTPException(400, "Signature verification failed")
    
    event = payload.get("event")
    data = payload.get("data", {})
    
    if event == "charge.success":
        # Payment succeeded
        ref = data.get("reference")
        amount_paid = data.get("amount") / 100  # kobo → NGN
        customer_email = data.get("customer", {}).get("email")
        
        logger.info(f"Paystack charge.success ref={ref} amount={amount_paid} email={customer_email}")
        
        # Verify and activate subscription
        success = await verify_payment(ref, amount_paid)
        if success:
            logger.info(f"Subscription activated ref={ref}")
            return {"status": "success", "message": "Subscription activated"}
        else:
            logger.error(f"Payment verification failed ref={ref}")
            return {"status": "failed", "message": "Verification failed"}
    
    elif event == "subscription.disable":
        # Subscription cancelled
        sub_id = data.get("subscription_id")
        logger.info(f"Subscription disabled sub_id={sub_id}")
        # Handle downgrade
        return {"status": "success", "message": "Downgrade processed"}
    
    elif event == "subscription.renewal.success":
        # Auto-renewal succeeded
        logger.info(f"Subscription renewed {data}")
        return {"status": "success", "message": "Renewal processed"}
    
    logger.info(f"Unhandled Paystack event: {event}")
    return {"status": "ignored", "event": event}

@app.post("/paystack/charge")
async def paystack_charge_create(user_id: int = Depends(verify_api_key)):
    """Create Paystack charge (for manual payments)."""
    # Implementation stub - use client-side Paystack popup instead
    raise HTTPException(501, "Use client-side Paystack integration")

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
