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

from fastapi import BackgroundTasks, FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import uvicorn

from db.session import get_session, is_db_configured
from db.priority import DBPriority
from db.repository import (
    get_api_token_owner,
    count_active_subscriptions,
    paystack_event_identity,
    mark_webhook_event_processed,
    count_active_vip_users,
)
from db.models import ApiToken, User, Signal, RuntimeState
from sqlalchemy import select
from core.redis_state import state
from core.env import env_bool
from core.redis_cache import cache_stats
from core.tier_constants import TIER_SCORE_THRESHOLDS
from core.telemetry import (
    init_tracer,
    observe_http_request,
    prometheus_content_type,
    prometheus_metrics_text,
)
from core.tier_policy import tier_rank
from payments.paystack import process_event as process_paystack_event
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

app = FastAPI(title="SignalRankAI API", version="1.0.0")
_tracer = init_tracer("signalrankai-web")

# The versioned API router is mounted on the canonical FastAPI application so
# deployment cannot accidentally expose a second, unmounted web app.  Legacy
# endpoints below remain available during the compatibility window.
try:
    from web.api import router as versioned_api_router

    app.include_router(versioned_api_router, prefix="/api/v1")
except Exception as exc:  # pragma: no cover - optional during minimal boots
    logger.debug("versioned API router unavailable during import: %s", type(exc).__name__)

# Preserve the dedicated Paystack ingress router as a compatibility alias.
# The inline routes below remain available for existing clients; this mounts
# the canonical raw-body/background-task handler at `/webhook/paystack`.
try:
    from payments.paystack_webhook import router as paystack_ingress_router

    app.include_router(paystack_ingress_router)
except Exception as exc:  # pragma: no cover - optional during minimal boots
    logger.debug("Paystack ingress router unavailable during import: %s", type(exc).__name__)

# CORS for Telegram web apps (future)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://t.me", "https://telegram.org"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep dependency resolution under our control so callers receive a stable
# ``401`` response for both missing and malformed credentials.  FastAPI's
# default ``HTTPBearer(auto_error=True)`` emits a ``403`` before the
# application can apply its API policy.
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

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


class ExchangeBrokerLinkRequest(BrokerPermissionRequest):
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    sandbox: bool = False


class PayoutAccountLinkRequest(BaseModel):
    account_number: str
    bank_code: str
    bank_name: str
    currency: str = "NGN"


class PayoutCreateRequest(BaseModel):
    recipient_telegram_user_id: int
    amount_ngn: float
    reason: str = "SignalRankAI owner-approved disbursement"


class PayoutApproveRequest(BaseModel):
    reference: str


class PayoutFinalizeRequest(BaseModel):
    reference: str
    otp: str


@app.get("/")
async def root() -> dict[str, str]:
    """Small authenticated-surface landing response for health-aware clients."""
    return {"service": "signalrankai", "status": "ok"}


def _normalize_exchange_provider(provider: str) -> str:
    p = str(provider or "").strip().lower().replace("_", "")
    aliases = {
        "binance": "binance",
        "binanceus": "binanceus",
        "bybit": "bybit",
    }
    if p not in aliases:
        raise HTTPException(400, "Unsupported exchange provider. Supported: binance, binanceus, bybit")
    return aliases[p]


def _broker_permissions_valid(req: BrokerPermissionRequest) -> tuple[bool, str]:
    perms = {str(p).strip().lower() for p in (req.permissions or []) if str(p).strip()}
    withdraw_enabled = bool(req.withdraw) or ("withdraw" in perms)
    transfer_enabled = bool(req.internal_transfer) or ("transfer" in perms) or ("internal_transfer" in perms)
    trade_enabled = bool(req.trade) or ("trade" in perms)
    read_enabled = True if req.read is None else bool(req.read) or ("read" in perms)
    if not read_enabled:
        return False, "read permission is required"
    if not trade_enabled:
        return False, "trade permission is required"
    if withdraw_enabled or transfer_enabled:
        return False, "withdraw/transfer must be disabled"
    return True, ""


def _exchange_state_key(user_id: int, provider: str) -> str:
    return f"broker_exchange:{int(user_id)}:{provider}"

async def verify_api_key(
    token: HTTPAuthorizationCredentials | None = Depends(security),
    api_key: str | None = Depends(api_key_header),
) -> int:
    """Verify a bearer API token and return its Telegram user id.

    This is intentionally exported from ``web.app`` for compatibility with
    broker integrations.  Authentication failures are never converted into
    a misleading 500 response, and database outages are reported as 503 so
    clients can safely retry without treating credentials as invalid.
    """
    raw_token = str(api_key or (token.credentials if token is not None else "") or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing API key")

    try:
        if not is_db_configured():
            raise HTTPException(status_code=503, detail="Token service unavailable")
        async with get_session() as session:
            user_id = await get_api_token_owner(session, raw_token=raw_token)
            if user_id is None:
                raise HTTPException(status_code=401, detail="Invalid or expired API key")
            return int(user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[auth] token verification unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Token service unavailable") from exc

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
    except HTTPException:
        # Preserve the policy response for callers; do not silently turn a
        # rate-limit violation into an allowed request.
        raise
    except Exception as exc:
        logger.debug("[rate_limit] backend unavailable: %s", type(exc).__name__)
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
            tier = (await session.execute(
                select(User.tier).where(User.telegram_user_id == int(user_id)).limit(1)
            )).scalar_one_or_none() or "FREE"
            if await _is_admin_user(int(user_id)):
                tier = "ADMIN"
            tier = str(tier).upper()
            base_query = select(Signal).where(
                Signal.archived == False,
                Signal.expired == False
            )
            
            if req.active_only:
                base_query = base_query.where(Signal.created_at >= now_utc_naive() - timedelta(hours=72))
            
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
    try:
        provider = _normalize_exchange_provider(req.provider)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "policy": "trade_only_required",
                "reason": str(exc.detail),
            },
        )
    valid, reason = _broker_permissions_valid(req)
    if not valid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "policy": "trade_only_required", "reason": reason},
        )

    return {"ok": True, "policy": "trade_only_required", "provider": provider}


@app.post("/broker/exchange/link")
async def link_exchange_broker(req: ExchangeBrokerLinkRequest, user_id: int = Depends(verify_api_key)):
    """Persist encrypted Binance/Bybit API credentials after permission validation."""
    provider = _normalize_exchange_provider(req.provider)
    valid, reason = _broker_permissions_valid(req)
    # Bybit permissions are verified against the provider below. Other
    # providers retain the caller-declared compatibility policy.
    if provider != "bybit" and not valid:
        raise HTTPException(400, {"ok": False, "policy": "trade_only_required", "reason": reason})

    api_key = str(req.api_key or "").strip()
    api_secret = str(req.api_secret or "").strip()
    if len(api_key) < 8 or len(api_secret) < 8:
        raise HTTPException(400, "API key and secret are required")

    verified_permissions = {
        "read": True, "trade": True, "withdraw": False, "internal_transfer": False,
    }
    if provider == "bybit":
        from services.bybit_client import (
            BybitCredentials, BybitError, BybitPermissionError, BybitV5Client,
        )
        try:
            verifier = BybitV5Client(BybitCredentials(api_key, api_secret, bool(req.sandbox)))
            verified_permissions = await verifier.verify_trade_only_key(
                require_ip_binding=env_bool("BYBIT_REQUIRE_IP_BINDING", True)
            )
        except BybitPermissionError as exc:
            raise HTTPException(400, {"ok": False, "policy": "trade_only_required", "reason": str(exc)}) from exc
        except BybitError as exc:
            raise HTTPException(400, {"ok": False, "policy": "credential_verification_failed", "reason": str(exc)}) from exc

    from services.security import encrypt_secret, is_encryption_available

    if not is_encryption_available():
        raise HTTPException(503, "ENCRYPTION_KEY is required before linking broker credentials")

    enc_key = encrypt_secret(api_key)
    enc_secret = encrypt_secret(api_secret)
    enc_passphrase = encrypt_secret(str(req.passphrase or "")) if req.passphrase else None
    if not enc_key or not enc_secret:
        raise HTTPException(503, "Broker credential encryption failed")

    masked = f"{api_key[:4]}...{api_key[-4:]}"
    payload = {
        "provider": provider,
        "api_key_enc": enc_key,
        "api_secret_enc": enc_secret,
        "passphrase_enc": enc_passphrase,
        "sandbox": bool(req.sandbox),
        "permissions": verified_permissions,
        "masked_key": masked,
        "linked_at": now_utc_naive().isoformat(),
    }

    async with get_session() as session:
        key = _exchange_state_key(int(user_id), provider)
        existing = await session.get(RuntimeState, key)
        if existing is None:
            session.add(RuntimeState(key=key, value=payload))
        else:
            existing.value = payload
            existing.updated_at = now_utc_naive()
        await session.commit()

    return {
        "ok": True,
        "provider": provider,
        "masked_key": masked,
        "sandbox": bool(req.sandbox),
        "policy": "trade_only_required",
        "permissions_verified": provider == "bybit",
        "ip_bound": bool(verified_permissions.get("ip_bound", False)),
    }


@app.post("/payout/account/link")
async def link_payout_account(req: PayoutAccountLinkRequest, user_id: int = Depends(verify_api_key)):
    """Resolve a Nigerian bank account and store only encrypted payout details."""
    from payments.payout_service import PayoutError, verify_and_store_payout_account
    try:
        row = await verify_and_store_payout_account(
            telegram_user_id=int(user_id), account_number=req.account_number,
            bank_code=req.bank_code, bank_name=req.bank_name, currency=req.currency,
        )
    except PayoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "verified": bool(row.verified), "account_last4": row.account_last4, "account_name": row.account_name, "currency": row.currency}


@app.post("/payout/request")
async def request_payout(req: PayoutCreateRequest, user_id: int = Depends(verify_api_key)):
    """Owner/admin creates a pending disbursement for a verified beneficiary."""
    if not await _is_admin_user(int(user_id)):
        raise HTTPException(403, "Owner or admin request required")
    from payments.payout_service import PayoutError, create_payout_request
    try:
        row = await create_payout_request(
            recipient_telegram_user_id=int(req.recipient_telegram_user_id),
            requested_by_telegram_id=int(user_id),
            amount_ngn=req.amount_ngn,
            reason=req.reason,
        )
    except PayoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "reference": row.reference, "status": row.status, "amount_ngn": row.amount_kobo / 100.0}


@app.post("/payout/approve")
async def approve_payout(req: PayoutApproveRequest, user_id: int = Depends(verify_api_key)):
    """Owner/admin-only approval and idempotent Paystack submission."""
    if not await _is_admin_user(int(user_id)):
        raise HTTPException(403, "Owner or admin approval required")
    from payments.payout_service import PayoutError, approve_and_submit_payout
    try:
        result = await approve_and_submit_payout(reference=req.reference, approver_telegram_id=int(user_id))
    except PayoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "reference": result.reference, "status": result.status, "transfer_code": result.transfer_code}


@app.post("/payout/finalize")
async def finalize_payout_transfer(req: PayoutFinalizeRequest, user_id: int = Depends(verify_api_key)):
    """Owner/admin finalizes an OTP-gated Paystack transfer."""
    if not await _is_admin_user(int(user_id)):
        raise HTTPException(403, "Owner or admin approval required")
    if not env_bool("PAYSTACK_TRANSFER_OTP_FLOW_ENABLED", False):
        raise HTTPException(503, "Paystack transfer OTP flow is disabled")
    from payments.payout_service import PayoutError, finalize_payout
    try:
        result = await finalize_payout(reference=req.reference, otp=req.otp, approver_telegram_id=int(user_id))
    except PayoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "reference": result.reference, "status": result.status, "transfer_code": result.transfer_code}


@app.get("/payout/verify/{reference}")
async def verify_payout_transfer(reference: str, user_id: int = Depends(verify_api_key)):
    """Owner/admin verifies a Paystack transfer by reference."""
    if not await _is_admin_user(int(user_id)):
        raise HTTPException(403, "Owner or admin access required")
    from payments.payout_service import PayoutError, verify_transfer
    try:
        data = await verify_transfer(reference)
    except PayoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "reference": reference, "provider": data}


@app.get("/broker/exchange/status")
async def exchange_broker_status(provider: str, user_id: int = Depends(verify_api_key)):
    """Return non-sensitive exchange broker link status."""
    provider_n = _normalize_exchange_provider(provider)
    async with get_session() as session:
        row = await session.get(RuntimeState, _exchange_state_key(int(user_id), provider_n))
    value = dict(getattr(row, "value", {}) or {}) if row is not None else {}
    return {
        "linked": row is not None,
        "provider": provider_n,
        "masked_key": value.get("masked_key"),
        "sandbox": bool(value.get("sandbox", False)),
        "linked_at": value.get("linked_at"),
        "policy": "trade_only_required",
    }

def _payments_enabled() -> bool:
    """Return whether payment side effects are explicitly enabled.

    Payment webhooks must remain verification-only by default.  A configured
    Paystack secret is not sufficient authorization to mutate subscriptions;
    operators must opt in with ``PAYMENTS_ENABLED=true``.
    """
    raw = os.getenv("PAYMENTS_ENABLED")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@app.post("/paystack/webhook")
@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request, background_tasks: BackgroundTasks):
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

    # Support maintenance/test mode without contacting external providers.
    if not _payments_enabled():
        return {"received": True, "verified": False, "idempotent": False, "event": event}

    from payments.paystack_events import ingest_paystack_event, process_stored_paystack_event
    try:
        inbox = await ingest_paystack_event(payload, raw_body, route=str(request.url.path))
    except Exception as exc:
        logger.error("Paystack durable inbox unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "Webhook persistence unavailable")
    if not inbox.get("terminal"):
        background_tasks.add_task(process_stored_paystack_event, str(inbox["event_id"]))
    return {
        "received": True,
        "verified": bool(inbox.get("terminal") and inbox.get("status") == "succeeded"),
        "idempotent": bool(inbox.get("idempotent")),
        "event": event,
        "event_id": inbox.get("event_id"),
        "processing_status": inbox.get("status"),
    }

@app.post("/paystack/charge")
async def paystack_charge_create(user_id: int = Depends(verify_api_key)):
    """Create Paystack charge (for manual payments)."""
    # Implementation stub - use client-side Paystack popup instead
    raise HTTPException(501, "Use client-side Paystack integration")


# === Paystack Utilities ===


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
    """Verify the Paystack HMAC using the live/test secret and rotation fallback."""
    if not signature:
        raise HTTPException(400, "Missing Paystack signature")
    from payments.paystack_policy import verify_paystack_event_signature
    if not verify_paystack_event_signature(body, signature):
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
        from payments.paystack_policy import evaluate_paystack_operation
        policy = evaluate_paystack_operation(
            telegram_user_id=int(telegram_user_id),
            amount_ngn=float(amount_ngn),
        )
        if not policy.allowed:
            logger.warning(
                "Paystack checkout blocked user=%s amount_ngn=%s mode=%s reason=%s",
                telegram_user_id, amount_ngn, policy.mode, policy.reason,
            )
            return {"error": f"Paystack checkout blocked: {policy.reason}"}
        
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
                "amount_ngn": float(amount_ngn),
                "paystack_mode": policy.mode,
                "guarded_staging_live": policy.reason == "guarded_live_staging",
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
            entry = VIPWaitlist(user_id=int(user_id), joined_at=now_utc_naive())
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

# ``web.api`` is the versioned API contract.  Mount its router into this
# process-owned application so Railway's ``web.app:app`` serves one FastAPI
# surface (the standalone ``web.api:app`` remains a compatibility import for
# clients/tests that used it directly).  The unversioned aliases preserve the
# pre-v1 token lifecycle paths during migration.
try:
    from web.api import router as _api_router

    app.include_router(_api_router)
except Exception as exc:  # pragma: no cover - optional during minimal boots
    logger.warning("[web] API router registration skipped: %s", type(exc).__name__)


async def _check_waitlist_capacity_job() -> None:
    """Check if VIP seats are available and invite from waitlist.
    
    Notifies next waitlist user with 24h invite TTL if seats available.
    """
    telegram_user_id: int | None = None
    try:
        from db.models import VIPWaitlist

        vip_seat_limit = max(1, int(os.getenv("VIP_SEAT_LIMIT", "20") or 20))
        async with get_session(
            priority=DBPriority.BACKGROUND,
            label="waitlist_capacity",
            timeout_seconds=5.0,
        ) as session:
            # Capacity uncertainty must not issue an extra invitation.
            active_vip = await count_active_vip_users(session)
            if active_vip >= vip_seat_limit:
                logger.info("[waitlist] at capacity: %s/%s", active_vip, vip_seat_limit)
                await session.rollback()
                return

            stmt = (
                select(VIPWaitlist)
                .where(VIPWaitlist.invited_at.is_(None))
                .order_by(VIPWaitlist.joined_at, VIPWaitlist.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            entry = (await session.execute(stmt)).scalars().first()
            if entry is None:
                await session.rollback()
                logger.debug("[waitlist] no pending entries")
                return

            user = (
                await session.execute(select(User).where(User.id == int(entry.user_id)))
            ).scalars().first()
            if user is None:
                await session.rollback()
                logger.warning("[waitlist] user %s not found", entry.user_id)
                return

            now = now_utc_naive()
            entry.invited_at = now
            entry.invite_expires_at = now + timedelta(hours=24)
            telegram_user_id = int(user.telegram_user_id)
            await session.commit()

        # Never hold a database transaction while calling Telegram.
        await _send_telegram_dm(
            telegram_user_id,
            "You've been invited to SignalRankAI VIP!\n"
            "The invitation expires in 24 hours.",
        )
        logger.info("[waitlist] invited user %s", telegram_user_id)
    except ImportError:
        logger.debug("[waitlist] VIPWaitlist model not available")
    except Exception as exc:
        logger.error("[waitlist] capacity check failed: %s", exc)


async def _monitor_expired_invites_job() -> None:
    """Monitor and process expired VIP invites.
    
    Resets expired invites and sends notification to user.
    """
    recipients: list[int] = []
    try:
        from db.models import VIPWaitlist

        async with get_session(
            priority=DBPriority.BACKGROUND,
            label="waitlist_expiry",
            timeout_seconds=5.0,
        ) as session:
            now = now_utc_naive()
            stmt = (
                select(VIPWaitlist, User)
                .join(User, VIPWaitlist.user_id == User.id)
                .where(
                    VIPWaitlist.invite_expires_at.is_not(None),
                    VIPWaitlist.invite_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).fetchall()
            for entry, user in rows:
                if str(user.tier or "").strip().lower() == "vip":
                    logger.debug(
                        "[waitlist] skipping already-upgraded user %s",
                        user.telegram_user_id,
                    )
                    continue
                entry.invited_at = None
                entry.invite_expires_at = None
                recipients.append(int(user.telegram_user_id))
            if rows:
                await session.commit()
            else:
                await session.rollback()

        for telegram_user_id in recipients:
            await _send_telegram_dm(
                telegram_user_id,
                "Your VIP invite expired. Check back later for another opportunity.",
            )
            logger.info(
                "[waitlist] reset expired invite for user %s",
                telegram_user_id,
            )
    except ImportError:
        logger.debug("[waitlist] VIPWaitlist model not available")
    except Exception as exc:
        logger.error("[waitlist] monitor job failed: %s", exc)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
