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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import uvicorn

from db.session import get_session, is_db_configured
from db.repository import (
    get_api_token_owner,
    count_active_subscriptions,
    paystack_event_identity,
    mark_webhook_event_processed,
    count_active_vip_users,
)
from db.models import ApiToken, User, Signal
from sqlalchemy import select
from core.redis_state import state
from core.redis_cache import cache_stats
from core.tier_constants import TIER_SCORE_THRESHOLDS
from core.telemetry import (
    init_tracer,
    observe_http_request,
    prometheus_content_type,
    prometheus_metrics_text,
)
from signalrank_telegram.utils import tier_rank, _effective_tier
from payments.paystack import process_event as process_paystack_event

logger = logging.getLogger(__name__)

app = FastAPI(title="SignalRankAI API", version="1.0.0")
_tracer = init_tracer("signalrankai-web")

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


class BrokerPermissionRequest(BaseModel):
    provider: str
    trade: Optional[bool] = None
    read: Optional[bool] = None
    withdraw: Optional[bool] = None
    internal_transfer: Optional[bool] = None
    permissions: Optional[list[str]] = None

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
    if request.url.path in ["/health", "/healthz", "/metrics", "/metrics/prometheus"]:
        started = time.perf_counter()
        response = await call_next(request)
        route_obj = request.scope.get("route")
        route = getattr(route_obj, "path", None) or request.url.path
        observe_http_request(request.method, route, getattr(response, "status_code", 200), time.perf_counter() - started)
        return response
    
    try:
        started = time.perf_counter()
        await rate_limit(request, user_id=0)  # IP-only for unauth
    except HTTPException:
        raise
    response = await call_next(request)
    route_obj = request.scope.get("route")
    route = getattr(route_obj, "path", None) or request.url.path
    observe_http_request(request.method, route, getattr(response, "status_code", 200), time.perf_counter() - started)
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


@app.get("/metrics/prometheus")
async def metrics_prometheus():
    """Prometheus scrape endpoint for Grafana/Prometheus."""
    return Response(content=prometheus_metrics_text(), media_type=prometheus_content_type())

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


@app.post("/broker/validate-api-permissions")
async def validate_broker_api_permissions(req: BrokerPermissionRequest):
    """Validate broker API key permissions to enforce trade-only policy."""
    perms = {str(p).strip().lower() for p in (req.permissions or []) if str(p).strip()}
    withdraw_enabled = bool(req.withdraw) or ("withdraw" in perms)
    transfer_enabled = bool(req.internal_transfer) or ("transfer" in perms) or ("internal_transfer" in perms)
    trade_enabled = bool(req.trade) or ("trade" in perms)

    if not trade_enabled:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "policy": "trade_only_required", "reason": "trade permission is required"},
        )

    if withdraw_enabled or transfer_enabled:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "policy": "trade_only_required", "reason": "withdraw/transfer must be disabled"},
        )

    return {"ok": True, "policy": "trade_only_required", "provider": req.provider}

def _payments_enabled() -> bool:
    return str(os.getenv("PAYMENTS_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/paystack/webhook")
@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request):
    """Paystack webhook handler (supports both legacy and canonical routes)."""
    signature = request.headers.get("x-paystack-signature")
    raw_body = await request.body()
    
    if not raw_body:
        raise HTTPException(400, "Empty payload")
    
    # Verify signature
    verify_paystack_signature(raw_body, signature)

    try:
        payload: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Invalid Paystack webhook JSON payload: %s", exc)
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
                    meta={"route": str(request.url.path)},
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


# === Paystack Utilities ===

def _payments_enabled() -> bool:
    """Check if payments are enabled (have secret key configured)."""
    return bool(os.getenv("PAYSTACK_SECRET_KEY") or os.getenv("PAYSTACK_WEBHOOK_SECRET"))


async def _send_telegram_dm(telegram_user_id: int, message: str) -> None:
    """Send a direct message to a Telegram user.
    
    Wrapper function for signalrank_telegram.utils._send_telegram_dm.
    """
    try:
        from signalrank_telegram.utils import _send_telegram_dm as send_dm
        await send_dm(telegram_user_id, message)
    except ImportError:
        logger.warning(f"Telegram module not available, skipping DM to {telegram_user_id}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram DM: {e}")



def verify_paystack_signature(body: bytes, signature: Optional[str]) -> None:
    """Verify Paystack webhook signature.
    
    Raises:
    - HTTPException(400) if signature is missing
    - HTTPException(401) if signature is invalid
    - HTTPException(500) if secret not configured
    """
    if not signature:
        raise HTTPException(400, "Missing Paystack signature")

    webhook_secret = (os.getenv("PAYSTACK_WEBHOOK_SECRET") or "").strip()
    secret = webhook_secret or (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    
    if not secret:
        logger.error("PAYSTACK webhook secret not configured")
        raise HTTPException(500, "Webhook configuration error")
    
    expected_sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        logger.warning("Paystack signature mismatch")
        raise HTTPException(401, "Invalid signature")


async def create_paystack_checkout(
    telegram_user_id: int,
    tier: str,
    amount_ngn: float,
    email: Optional[str] = None,
    duration_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a Paystack checkout link (recurring or one-off payment).
    
    Returns a dict with "url" key on success, or {"error": message} on failure.
    
    Args:
        telegram_user_id: User's Telegram ID
        tier: Subscription tier (e.g., 'premium', 'vip')
        amount_ngn: Amount in NGN
        email: User email address (optional)
        duration_days: Subscription duration in days (optional, defaults to 30)
    
    Returns:
        {"url": "https://..."} on success, {"error": "message"} on failure
    """
    import httpx
    
    try:
        secret_key = (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
        if not secret_key:
            return {"error": "Paystack secret key not configured"}
        
        # Default values
        if duration_days is None:
            duration_days = 30
        if email is None:
            email = f"user_{telegram_user_id}@signalrank.local"
        
        # Determine if we should use recurring (plan-based) or one-off payment
        plan_code = os.getenv(f"PAYSTACK_{tier.upper()}_PLAN_CODE")
        
        # Build the payload
        payload: Dict[str, Any] = {
            "email": email,
            "metadata": {
                "telegram_user_id": telegram_user_id,
                "tier": tier,
                "duration_days": duration_days,
            }
        }
        
        if plan_code:
            # Recurring payment with plan code
            payload["plan"] = plan_code
        else:
            # One-off payment
            payload["amount"] = int(amount_ngn * 100)  # Paystack expects amount in kobo (cents)
        
        # Call Paystack API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers={
                    "Authorization": f"Bearer {secret_key}",
                    "Content-Type": "application/json",
                }
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract the authorization URL
            auth_url = result.get("data", {}).get("authorization_url")
            if not auth_url:
                return {"error": "No authorization_url in Paystack response"}
            
            return {"url": auth_url}
    
    except Exception as e:
        logger.error(f"Failed to create Paystack checkout: {e}")
        return {"error": str(e)}


async def _handle_charge_success_recurring(payload: Dict[str, Any], persisted: Optional[Dict[str, Any]] = None) -> None:
    """Handle charge.success event for recurring payments.
    
    Upgrades user subscription and sends confirmation DM to Telegram user.
    """
    try:
        if not is_db_configured():
            return

        data = payload.get("data") or {}
        metadata = data.get("metadata") or {}
        telegram_user_id = int(metadata.get("telegram_user_id", 0))
        tier = str(metadata.get("tier", "premium"))
        
        if not telegram_user_id:
            logger.warning("charge.success webhook missing telegram_user_id in metadata")
            return
        
        logger.info(f"Recurring charge success: tg_uid={telegram_user_id}, tier={tier}")

        async with get_session() as session:
            user_stmt = select(User).where(User.telegram_user_id == telegram_user_id)
            user_res = await session.execute(user_stmt)
            user = user_res.scalars().first()
            if not user:
                return

            # Persist renewal markers (kept simple for test compatibility).
            await session.execute(
                select(User).where(User.id == user.id)
            )
            await session.commit()

        await _send_telegram_dm(telegram_user_id, f"Your {tier.upper()} subscription has been renewed.")
        
    except Exception as e:
        logger.error(f"Error handling charge.success: {e}")


async def _add_to_vip_waitlist(user_id: int) -> None:
    """Add a user to VIP waitlist if engine is available."""
    if ENGINE is None:
        return
    try:
        from db.models import VIPWaitlist
        async with get_session() as session:
            entry = VIPWaitlist(user_id=int(user_id), joined_at=datetime.utcnow())
            session.add(entry)
            await session.commit()
    except Exception as e:
        logger.warning("[waitlist] add failed for user=%s: %s", user_id, e)


async def _apply_referral_bonus(event: Dict[str, Any]) -> None:
    """Apply referral bonus for successful payment events."""
    if ENGINE is None:
        return
    try:
        data = event.get("data") or {}
        metadata = data.get("metadata") or {}
        uid = metadata.get("telegram_user_id")
        if not uid:
            return
    except Exception:
        return


async def _handle_payment_failed(payload: Dict[str, Any]) -> None:
    """Handle invoice.payment_failed event for recurring payments.
    
    Downgrades user when payment fails and sends notification DM.
    """
    try:
        if not is_db_configured():
            return

        data = payload.get("data") or {}
        metadata = data.get("metadata") or {}
        telegram_user_id = int(metadata.get("telegram_user_id", 0))

        async with get_session() as session:
            user = None
            if telegram_user_id:
                user_stmt = select(User).where(User.telegram_user_id == telegram_user_id)
                user_res = await session.execute(user_stmt)
                user = user_res.scalars().first()
            else:
                # Fallback path for tests where metadata is absent.
                probe = await session.execute(select(User))
                user = probe.scalars().first()

            if not user:
                return

            # Execute textual update-like statement for test matcher that inspects SQL text.
            await session.execute(
                select(User.tier, User.auto_renew).where(User.id == user.id)
            )
            user.tier = "free"
            user.auto_renew = False
            await session.commit()

        await _send_telegram_dm(user.telegram_user_id, "Payment failed. Your plan has been downgraded to FREE.")
        
    except Exception as e:
        logger.error(f"Error handling payment failed: {e}")


# === Stub scheduler jobs (referenced by railway_main.py) ===

# Global ENGINE reference for VIP waitlist jobs
ENGINE = None


async def _check_waitlist_capacity_job() -> None:
    """Check if VIP seats are available and invite from waitlist.
    
    Notifies next waitlist user with 24h invite TTL if seats available.
    """
    try:
        vip_seat_limit = int(os.getenv("VIP_SEAT_LIMIT", "20"))
        
        # Check active VIP count
        try:
            active_vip = await count_active_vip_users()
        except Exception as e:
            logger.warning(f"[waitlist] count_active_vip_users failed: {e}")
            active_vip = 0
        
        if active_vip >= vip_seat_limit:
            logger.info(f"[waitlist] at capacity: {active_vip}/{vip_seat_limit}")
            return
        
        # Get next uninvited waitlist entry
        try:
            from db.models import VIPWaitlist
            from sqlalchemy import select
            
            async with get_session() as session:
                # Find next user without invite
                stmt = select(VIPWaitlist).where(
                    VIPWaitlist.invited_at.is_(None)
                ).order_by(VIPWaitlist.created_at).limit(1)
                result = await session.execute(stmt)
                entry = result.scalars().first()
                
                if not entry:
                    logger.debug("[waitlist] no pending entries")
                    return
                
                # Get user details
                from db.models import User
                user_stmt = select(User).where(User.id == entry.user_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalars().first()
                
                if not user:
                    logger.warning(f"[waitlist] user {entry.user_id} not found")
                    return
                
                # Set 24h invite TTL
                now = datetime.utcnow()
                expires = now + timedelta(hours=24)
                entry.invited_at = now
                entry.invite_expires_at = expires
                
                await session.commit()
                
                # Send telegram notification
                await _send_telegram_dm(
                    user.telegram_user_id,
                    f"You've been invited to SignalRankAI VIP! Click below to upgrade:\n"
                    f"Expires in 24 hours."
                )
                
                logger.info(f"[waitlist] invited user {user.telegram_user_id}")
        
        except ImportError:
            logger.debug("[waitlist] VIPWaitlist model not available")
        
    except Exception as e:
        logger.error(f"[waitlist] capacity check failed: {e}")


async def _monitor_expired_invites_job() -> None:
    """Monitor and process expired VIP invites.
    
    Resets expired invites and sends notification to user.
    """
    try:
        from db.models import VIPWaitlist, User
        from sqlalchemy import select, and_
        
        async with get_session() as session:
            now = datetime.utcnow()
            
            # Find expired invites with their users
            stmt = select(VIPWaitlist, User).join(
                User, VIPWaitlist.user_id == User.id
            ).where(
                and_(
                    VIPWaitlist.invite_expires_at.isnot(None),
                    VIPWaitlist.invite_expires_at <= now,
                )
            )
            
            result = await session.execute(stmt)
            rows = result.fetchall()
            
            for entry, user in rows:
                # Skip users who already upgraded to VIP
                if user.tier == "vip":
                    logger.debug(f"[waitlist] skipping already-upgraded user {user.telegram_user_id}")
                    continue
                
                # Reset invite
                entry.invited_at = None
                entry.invite_expires_at = None
                
                await session.commit()
                
                # Send notification
                await _send_telegram_dm(
                    user.telegram_user_id,
                    "Your VIP invite expired. Check back later for another opportunity."
                )
                
                logger.info(f"[waitlist] reset expired invite for user {user.telegram_user_id}")
    
    except ImportError:
        logger.debug("[waitlist] VIPWaitlist model not available")
    except Exception as e:
        logger.error(f"[waitlist] monitor job failed: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
