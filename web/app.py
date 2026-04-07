import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from config import config
import socket
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from db.session import get_session
from db.repository import (
    activate_subscription,
    count_active_vip_users,
    get_active_subscription,
    mark_webhook_event_processed,
    paystack_event_identity,
)
from db.session import is_db_configured
from core.redis_state import state


APP_NAME = "SignalRankAI"
logger = logging.getLogger(__name__)

# Optional global ENGINE placeholder (set by runtime if needed). Tests expect it to exist.
ENGINE = None

request_latency = Histogram(
    "signalrankai_http_request_latency_seconds",
    "HTTP request latency",
    labelnames=("path", "method", "status"),
)

paystack_webhook_processing_seconds = Histogram(
    "signalrankai_paystack_webhook_processing_seconds",
    "Paystack webhook processing latency",
    labelnames=("event_type", "status"),
)

ml_scoring_execution_seconds = Histogram(
    "signalrankai_ml_scoring_execution_seconds",
    "ML scoring execution latency",
    labelnames=("model", "status"),
)

telegram_dispatch_latency_seconds = Histogram(
    "signalrankai_telegram_dispatch_latency_seconds",
    "Telegram dispatch latency",
    labelnames=("status",),
)

db_pool_utilization_ratio = Histogram(
    "signalrankai_db_pool_utilization_ratio",
    "Approximate DB pool utilization ratio",
)

webhook_failures = Counter(
    "signalrankai_paystack_webhook_failures_total",
    "Total Paystack webhook failures",
    labelnames=("reason",),
)




def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return bool(default)
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


def verify_paystack_signature(raw_body: bytes, signature_header: Optional[str]) -> None:
    """Verify Paystack webhook HMAC signature.

    Raises HTTPException on failure so route handlers can return appropriate codes.
    Order of checks:
      1. Missing signature header → 400 (client error, regardless of secret config)
      2. Missing secret → 500 (server misconfiguration)
      3. Bad signature → 401
    """
    # Always 400 when signature header is absent — do this before secret lookup
    if not signature_header:
        webhook_failures.labels(reason="missing_signature").inc()
        raise HTTPException(status_code=400, detail="Missing x-paystack-signature")

    # Read fresh from environment so tests that set os.environ after module import work
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET") or os.getenv("PAYSTACK_SECRET_KEY")
    if not secret:
        webhook_failures.labels(reason="missing_secret").inc()
        raise HTTPException(status_code=500, detail="Paystack secret not configured")

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    if not _constant_time_equals(digest, signature_header.strip()):
        webhook_failures.labels(reason="bad_signature").inc()
        raise HTTPException(status_code=401, detail="Invalid signature")


async def confirm_paystack_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Confirm webhook event with Paystack API.

    For local/dev, you can set PAYMENTS_ENABLED=false to bypass external verification
    (tests should use mocked HTTPX).
    """

    if not _env_bool("PAYMENTS_ENABLED", False):
        return {"ok": True, "mode": "payments_disabled"}

    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="PAYSTACK_SECRET_KEY not configured")

    data = event.get("data") or {}
    reference = data.get("reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Missing reference")

    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {secret_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail="Paystack verify failed")
        payload = resp.json()

    ok = bool(payload.get("status")) and (payload.get("data") or {}).get("status") == "success"
    return {"ok": ok, "verified": ok, "paystack": payload}


def _extract_subscription_fields(event: Dict[str, Any]) -> Tuple[int, Optional[str], Optional[int], Optional[str], Dict[str, Any]]:
    data = event.get("data") or {}
    meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}

    # Prefer explicit metadata fields set when generating the payment link.
    telegram_user_id = meta.get("telegram_user_id") or meta.get("user_id")
    reference = data.get("reference") if isinstance(data, dict) else None

    try:
        telegram_user_id_int = int(telegram_user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Missing telegram_user_id in metadata") from exc

    meta_out: Dict[str, Any] = {
        "raw_event": event.get("event"),
        "metadata": meta,
        "received_at": datetime.utcnow().isoformat() + "Z",
    }
    return telegram_user_id_int, None, None, reference, meta_out


def _map_amount_to_tier(amount_ngn: int) -> tuple[str, int] | None:
    mapping = {
        40000: ("vip", 30),
        8000: ("premium", 7),
        24000: ("premium", 30),
        56000: ("premium", 90),
    }
    return mapping.get(int(amount_ngn))


async def _persist_subscription_if_configured(event: Dict[str, Any]) -> Dict[str, Any]:
    if not is_db_configured():
        return {"persisted": False, "reason": "DATABASE_URL not set"}

    try:
        telegram_user_id, _, _, reference, meta = _extract_subscription_fields(event)
    except HTTPException as exc:
        # Not all Paystack webhook events contain our subscription metadata.
        # If the signature is valid, acknowledge receipt and simply skip persistence.
        return {"persisted": False, "reason": str(getattr(exc, "detail", "unable_to_persist"))}
    data = event.get("data") or {}
    meta_in = (data.get("metadata") or {}) if isinstance(data, dict) else {}
    amount_kobo = 0
    try:
        amount_kobo = int(data.get("amount") or 0)
    except Exception:
        amount_kobo = 0
    amount_ngn = max(0, int(amount_kobo) // 100)
    currency = None
    try:
        currency = str(data.get("currency") or "").strip() or None
    except Exception:
        currency = None

    mapped = _map_amount_to_tier(amount_ngn)
    if not mapped:
        return {"persisted": False, "reason": f"amount_mismatch ({amount_ngn})"}
    tier, duration_days = mapped

    async with get_session() as session:
        # Record payment event (best-effort; idempotent).
        try:
            from db.pg_features import record_payment_event

            kind = "subscription"
            try:
                if (meta_in.get("duration") == "EXTRA") or (meta_in.get("extra_count") is not None):
                    kind = "extra_signals"
            except Exception:
                kind = "subscription"

            await record_payment_event(
                session,
                telegram_user_id=int(telegram_user_id),
                paystack_reference=str(reference or ""),
                amount_ngn=int(amount_ngn),
                currency=currency,
                kind=kind,
                tier=str(tier).strip().lower(),
                duration_days=int(duration_days) if duration_days is not None else None,
                plan_code=(str(meta_in.get("plan_code")) if meta_in.get("plan_code") else None),
                meta={"event": event.get("event"), "metadata": meta_in},
            )
        except Exception:
            pass

        # VIP seats: max N active VIP subscribers (excludes owners + temp owner bypass)
        tier_norm = str(tier).strip().lower()
        if tier_norm == "vip":
            vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15") or "15")
            exclude_ids = set(getattr(__import__("config"), "OWNER_IDS", set()) or set())
            try:
                if await state.has_temp_owner(telegram_user_id):
                    exclude_ids.add(int(telegram_user_id))
            except Exception:
                pass

            active_for_user = await get_active_subscription(session, telegram_user_id=telegram_user_id, tier="vip")
            if active_for_user is None:
                used = await count_active_vip_users(session, exclude_telegram_user_ids=exclude_ids)
                if used >= max(1, vip_limit) and int(telegram_user_id) not in exclude_ids:
                    return {"persisted": False, "reason": f"vip_full ({vip_limit} seats)"}

        sub = await activate_subscription(
            session=session,
            telegram_user_id=telegram_user_id,
            tier=tier,
            duration_days=duration_days,
            paystack_reference=reference,
            meta=meta,
        )
        await session.commit()
        return {"persisted": True, "subscription_id": sub.id, "tier": sub.tier}


async def _check_waitlist_capacity_job() -> None:
    """Pop the oldest uninvited VIP waitlist entry when a seat becomes available.

    - Counts active VIP subscribers; if below VIP_SEAT_LIMIT, invites the oldest
      uninvited entry: sets invited_at + invite_expires_at = now + 24 h, DMs the user.
    Scheduled: every 1 hour via the FastAPI lifespan AsyncIOScheduler.
    """
    if not is_db_configured():
        return
    try:
        from db.models import VIPWaitlist, User
        from sqlalchemy import select, update as sa_update
        from datetime import timedelta

        vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15"))

        async with get_session() as session:
            # Count current active VIP subscribers
            used = await count_active_vip_users(session)
            if used >= vip_limit:
                return  # Still at capacity

            # Find oldest uninvited waitlist entry
            result = await session.execute(
                select(VIPWaitlist)
                .where(VIPWaitlist.invited_at.is_(None))
                .order_by(VIPWaitlist.joined_at.asc())
                .limit(1)
            )
            entry = result.scalars().first()
            if not entry:
                return  # Waitlist is empty

            # Look up the user for their telegram_user_id
            user_res = await session.execute(
                select(User).where(User.id == entry.user_id)
            )
            user = user_res.scalars().first()
            if not user:
                # Orphaned entry — clean up
                await session.delete(entry)
                await session.commit()
                return

            # Set invite TTL = 24 h from now
            now = datetime.utcnow()
            expires = now + timedelta(hours=24)
            await session.execute(
                sa_update(VIPWaitlist).where(VIPWaitlist.id == entry.id).values(
                    invited_at=now,
                    invite_expires_at=expires,
                    notified_at=now,
                )
            )
            await session.commit()

            # Generate a Paystack checkout link for VIP
            link = ""
            try:
                vip_price = int(os.getenv("VIP_PRICE_NGN", "30000"))
                checkout = await create_paystack_checkout(
                    telegram_user_id=user.telegram_user_id,
                    tier="vip",
                    amount_ngn=vip_price,
                    email=f"user{user.telegram_user_id}@signalrank.ai",
                    duration_days=30,
                )
                link = checkout.get("url", "")
            except Exception as _le:
                logger.warning(f"[waitlist] Checkout link generation failed: {_le}")

            link_text = f"\n\n[\U0001f680 Complete Your VIP Upgrade Now]({link})" if link else ""
            await _send_telegram_dm(
                user.telegram_user_id,
                f"\U0001f6a8 *VIP SPOT UNLOCKED!*\n\n"
                f"A seat has opened up just for you. You have exactly *24 hours* to "
                f"complete your payment before this link expires and the spot is passed "
                f"to the next trader in line."
                + link_text
                + f"\n\n\u23f0 Link expires: *{expires.strftime('%Y-%m-%d %H:%M')} UTC*",
            )
            logger.info(
                f"[waitlist] Invited user {user.telegram_user_id}, expires {expires}"
            )
    except Exception as exc:
        logger.warning(f"[waitlist] check_waitlist_capacity_job failed: {exc}")


async def _monitor_expired_invites_job() -> None:
    """Expire VIP invitations not acted upon within 24 hours.

    - Finds entries where invite_expires_at < now AND user has not upgraded to VIP.
    - Resets invited_at + invite_expires_at = NULL (re-queues for next cycle).
    - DMs the user that their spot was passed on.
    - Triggers _check_waitlist_capacity_job to immediately fill any freed seat.
    Scheduled: every 15 minutes via the FastAPI lifespan AsyncIOScheduler.
    """
    if not is_db_configured():
        return
    try:
        from db.models import VIPWaitlist, User
        from sqlalchemy import select, update as sa_update

        now = datetime.utcnow()
        expired_count = 0

        async with get_session() as session:
            result = await session.execute(
                select(VIPWaitlist, User)
                .join(User, User.id == VIPWaitlist.user_id)
                .where(
                    VIPWaitlist.invite_expires_at.is_not(None),
                    VIPWaitlist.invite_expires_at < now,
                    User.tier != "vip",
                )
            )
            expired_rows = result.fetchall()

            for entry, user in expired_rows:
                # Reset invite columns — entry stays on waitlist for next cycle
                await session.execute(
                    sa_update(VIPWaitlist).where(VIPWaitlist.id == entry.id).values(
                        invited_at=None,
                        invite_expires_at=None,
                    )
                )
                await _send_telegram_dm(
                    user.telegram_user_id,
                    "\u23f3 *VIP Invite Expired*\n\n"
                    "Your 24-hour VIP spot has been passed to the next trader in line. "
                    "Don't worry \u2014 you're still on the waitlist and will be notified "
                    "again when the next seat opens.\n\n"
                    "You can also try /upgrade directly if more seats open. \U0001f64f",
                )
                expired_count += 1

            if expired_count:
                await session.commit()
                logger.info(
                    f"[waitlist] Expired {expired_count} VIP invite(s); re-queued for next cycle"
                )
                # Immediately check whether a freshly freed seat can be filled
                await _check_waitlist_capacity_job()
    except Exception as exc:
        logger.warning(f"[waitlist] monitor_expired_invites_job failed: {exc}")


async def _send_waitlist_reminder_job() -> None:
    """Send one 12-hour reminder to invited waitlist users before 24h expiry."""
    if not is_db_configured():
        return
    try:
        from db.models import VIPWaitlist, User
        from sqlalchemy import select, update as sa_update
        from datetime import timedelta

        now = datetime.utcnow()
        win_start = now + timedelta(hours=11, minutes=45)
        win_end = now + timedelta(hours=12, minutes=15)
        reminded = 0

        async with get_session() as session:
            result = await session.execute(
                select(VIPWaitlist, User)
                .join(User, User.id == VIPWaitlist.user_id)
                .where(
                    VIPWaitlist.invited_at.is_not(None),
                    VIPWaitlist.invite_expires_at.is_not(None),
                    VIPWaitlist.invite_expires_at >= win_start,
                    VIPWaitlist.invite_expires_at <= win_end,
                    User.tier != "vip",
                )
            )
            rows = result.fetchall()

            for entry, user in rows:
                try:
                    invited_at = getattr(entry, "invited_at", None)
                    notified_at = getattr(entry, "notified_at", None)
                    # Send reminder once: only while notified_at still equals original invite ping.
                    if invited_at is None:
                        continue
                    if notified_at is not None and abs((notified_at - invited_at).total_seconds()) > 120:
                        continue
                except Exception:
                    pass

                expires = getattr(entry, "invite_expires_at", None)
                exp_txt = expires.strftime("%Y-%m-%d %H:%M UTC") if expires else "soon"
                await _send_telegram_dm(
                    user.telegram_user_id,
                    "⏰ *VIP Invite Reminder*\n\n"
                    "Your VIP checkout invite is still active, but your 24-hour window is halfway gone.\n"
                    f"Expiry time: *{exp_txt}*\n\n"
                    "Complete your upgrade before expiry to secure your seat.",
                )
                await session.execute(
                    sa_update(VIPWaitlist).where(VIPWaitlist.id == entry.id).values(
                        notified_at=now,
                    )
                )
                reminded += 1

            if reminded:
                await session.commit()
                logger.info(f"[waitlist] Sent {reminded} half-life reminder(s)")
    except Exception as exc:
        logger.warning(f"[waitlist] send_waitlist_reminder_job failed: {exc}")


@asynccontextmanager
async def _lifespan(app_: FastAPI):
    """FastAPI lifespan: start waitlist scheduler.

    DB migrations are handled by main.py::run_startup_ops() with a
    pg_advisory_lock BEFORE uvicorn starts.  Running alembic upgrade again
    inside the lifespan would attempt to acquire the same lock, block the
    event-loop thread, and prevent FastAPI from ever emitting
    'Application startup complete' — causing Railway healthchecks to fail.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    # Start AsyncIOScheduler for waitlist TTL background jobs
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _check_waitlist_capacity_job,
        "interval",
        hours=1,
        id="wl_capacity",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _monitor_expired_invites_job,
        "interval",
        minutes=15,
        id="wl_monitor",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _send_waitlist_reminder_job,
        "interval",
        minutes=15,
        id="wl_reminder_12h",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("[lifespan] Waitlist scheduler started (capacity=1h, monitor=15min, reminder=15min)")

    yield  # ── Application runs ──────────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    _scheduler.shutdown(wait=False)
    logger.info("[lifespan] Waitlist scheduler stopped")



app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=_lifespan)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"[web] HTTP {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"[web] HTTP {request.method} {request.url} -> {response.status_code}")
    return response

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method
    started = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        elapsed = max(0.0, time.perf_counter() - started)
        request_latency.labels(path=path, method=method, status=status).observe(elapsed)
        try:
            from db.session import get_engine_for_event_loop
            eng = get_engine_for_event_loop()
            if eng is not None:
                pool = getattr(getattr(eng, "sync_engine", None), "pool", None)
                if pool is not None and hasattr(pool, "checkedout") and hasattr(pool, "size"):
                    size = max(1, int(pool.size() or 1))
                    checked = max(0, int(pool.checkedout() or 0))
                    db_pool_utilization_ratio.observe(min(1.0, float(checked) / float(size)))
        except Exception:
            pass


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint for Railway."""
    # Allow a very small/basic health response when running on Railway or when
    # explicitly requested via RAILWAY_HEALTH_BASIC. This avoids failing platform
    # healthchecks during startup when DB/Redis may not yet be available.
    if (os.getenv("RAILWAY_HEALTH_BASIC") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "service": APP_NAME,
            "railway_basic": True,
        }

    # If Railway environment variables are present, prefer a lightweight success
    # to allow the platform to mark the deployment as healthy while the app
    # finishes background startup tasks.
    if os.getenv("RAILWAY_SERVICE_NAME"):
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "service": APP_NAME,
            "railway_basic": True,
        }

    checks = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": APP_NAME,
        "run_mode": (os.getenv("RUN_MODE") or "").strip().lower() or None,
        "hostname": socket.gethostname(),
        "railway": {
            "service_name": os.getenv("RAILWAY_SERVICE_NAME"),
            "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME"),
            "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID"),
            "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA"),
        },
    }
    
    # Check database
    try:
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        checks["status"] = "degraded"
    
    # Shared state backend check (Postgres-backed)
    try:
        state.set_sync("health_check", "ok", ex=60)
        checks["state_backend"] = "ok"
    except Exception:
        checks["state_backend"] = "unavailable"
        checks["status"] = "degraded"
    
    return checks


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


# Lightweight health endpoint for simple load-balancer/railway checks
@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    """Very small health endpoint that does not touch DB or Redis.

    Use this for platform healthchecks that should succeed even when
    backing services are not available during deploy/startup.
    """
    return {
        "status": "ok",
        "service": APP_NAME,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/ready")
async def ready() -> Dict[str, Any]:
    """Readiness endpoint that checks DB and shared state accessibility."""
    checks: Dict[str, Any] = {"status": "ok", "service": APP_NAME}
    try:
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        checks["status"] = "degraded"
        checks["database"] = f"error: {exc}"
    else:
        checks["database"] = "ok"
    try:
        state.set_sync("ready_check", "ok", ex=30)
        checks["state_backend"] = "ok"
    except Exception as exc:
        checks["status"] = "degraded"
        checks["state_backend"] = f"error: {exc}"
    return checks


def _require_admin_token(x_admin_token: Optional[str]) -> None:
    expected = os.getenv("ADMIN_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="ADMIN_API_TOKEN not configured")
    if not x_admin_token or not _constant_time_equals(expected, x_admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/admin/killswitch")
async def get_killswitch(x_admin_token: Optional[str] = Header(default=None, alias="x-admin-token")):
    _require_admin_token(x_admin_token)
    ks = await state.get_killswitch()
    return {"enabled": ks.enabled, "reason": ks.reason, "updated_at": ks.updated_at}


@app.post("/admin/killswitch")
async def set_killswitch(
    request: Request,
    x_admin_token: Optional[str] = Header(default=None, alias="x-admin-token"),
):
    _require_admin_token(x_admin_token)
    payload = await request.json()
    enabled = bool(payload.get("enabled", False))
    reason = str(payload.get("reason", ""))
    close_all_positions = bool(payload.get("close_all_positions", False))
    await state.set_killswitch(enabled=enabled, reason=reason)

    closed_summary = None
    if enabled and close_all_positions:
        try:
            from sqlalchemy import text
            from services.mt5_client import close_all_positions as _close_all_positions

            attempted_accounts = 0
            attempted_positions = 0
            closed_positions = 0
            async with get_session() as session:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT c.metaapi_account_id
                            FROM mt5_credentials c
                            WHERE c.metaapi_account_id IS NOT NULL
                            """
                        )
                    )
                ).fetchall()
                for (account_id,) in rows:
                    try:
                        if not account_id:
                            continue
                        attempted_accounts += 1
                        res = await _close_all_positions(str(account_id), comment="SignalRankAI-KillSwitch")
                        attempted_positions += int(res.get("attempted", 0) or 0)
                        closed_positions += int(res.get("closed", 0) or 0)
                    except Exception:
                        continue
                await session.commit()

            closed_summary = {
                "attempted_accounts": attempted_accounts,
                "attempted_positions": attempted_positions,
                "closed_positions": closed_positions,
            }
        except Exception as exc:
            closed_summary = {"error": str(exc)}

    ks = await state.get_killswitch()
    return {
        "enabled": ks.enabled,
        "reason": ks.reason,
        "updated_at": ks.updated_at,
        "close_all_positions": closed_summary,
    }


async def _send_telegram_dm(telegram_user_id: int, text: str) -> None:
    """Fire-and-forget Telegram DM from the web layer (uses Bot API directly)."""
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                # Use plain text to avoid MarkdownV2 escaping issues that can drop messages.
                json={"chat_id": telegram_user_id, "text": text},
            )
            if resp.status_code >= 400:
                logger.warning(
                    "[dm] Telegram API sendMessage failed chat_id=%s status=%s body=%s",
                    telegram_user_id,
                    resp.status_code,
                    (resp.text or "")[:300],
                )
    except Exception as _e:
        logger.warning(f"[dm] Failed to send DM to {telegram_user_id}: {_e}")


@app.post("/webhooks/paystack")
@app.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(default=None, alias="x-paystack-signature"),
) -> JSONResponse:
    _started = time.perf_counter()
    raw = await request.body()
    verify_paystack_signature(raw, x_paystack_signature)

    event = await request.json()
    event_type = str(event.get("event") or "")
    event_id, payload_hash = paystack_event_identity(event, raw)
    reference = str((event.get("data") or {}).get("reference") or "").strip() or None

    # ── Payment failure: no reference to confirm — handle directly then ACK ───
    if event_type == "invoice.payment_failed":
        await _handle_payment_failed(event)
        paystack_webhook_processing_seconds.labels(
            event_type=event_type or "unknown", status="ok"
        ).observe(max(0.0, time.perf_counter() - _started))
        return JSONResponse({"received": True, "event": event_type})

    confirmation = await confirm_paystack_event(event)
    if not confirmation.get("ok"):
        raise HTTPException(status_code=400, detail="Payment not verified")

    if is_db_configured():
        async with get_session() as _session:
            inserted = await mark_webhook_event_processed(
                _session,
                provider="paystack",
                event_id=event_id,
                event_type=event_type,
                reference=reference,
                payload_hash=payload_hash,
                meta={"dedupe_stage": "verified"},
            )
            await _session.commit()
        if not inserted:
            paystack_webhook_processing_seconds.labels(
                event_type=event_type or "unknown", status="idempotent"
            ).observe(max(0.0, time.perf_counter() - _started))
            return JSONResponse({"received": True, "idempotent": True, "event": event_type})

    persisted = await _persist_subscription_if_configured(event)
    if persisted.get("persisted") is False and str(persisted.get("reason", "")).startswith("vip_full"):
        # Auto-add to waitlist
        try:
            data = event.get("data") or {}
            meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}
            uid = int(meta.get("telegram_user_id") or meta.get("user_id") or 0)
            if uid:
                await _add_to_vip_waitlist(uid)
        except Exception:
            pass
        paystack_webhook_processing_seconds.labels(
            event_type=event_type or "unknown", status="conflict"
        ).observe(max(0.0, time.perf_counter() - _started))
        raise HTTPException(status_code=409, detail="VIP is currently full. You have been added to the waitlist.")

    # ── Referral bonus ────────────────────────────────────────────────────
    if persisted.get("persisted"):
        await _apply_referral_bonus(event)

    # ── Recurring billing: save codes + send renewal DM on auto-charge ───
    if event_type == "charge.success":
        await _handle_charge_success_recurring(event, persisted)

    paystack_webhook_processing_seconds.labels(
        event_type=event_type or "unknown", status="ok"
    ).observe(max(0.0, time.perf_counter() - _started))
    return JSONResponse(
        {
            "received": True,
            "verified": bool(confirmation.get("verified", False)),
            "persisted": persisted.get("persisted", False),
        }
    )


async def _add_to_vip_waitlist(telegram_user_id: int) -> None:
    """Insert a row into vip_waitlist if not already present."""
    if not is_db_configured():
        return
    try:
        from db.models import VIPWaitlist
        from sqlalchemy import select
        from db.models import User, ReferralReward

        async with get_session() as session:
            user_row = await session.execute(
                select(User).where(User.telegram_user_id == int(telegram_user_id))
            )
            user = user_row.scalars().first()
            if not user:
                return
            exists = await session.execute(
                select(VIPWaitlist).where(VIPWaitlist.user_id == user.id)
            )
            if exists.scalars().first() is None:
                session.add(
                    VIPWaitlist(
                        user_id=user.id,
                        joined_at=datetime.utcnow(),
                    )
                )
                await session.commit()
                logger.info(f"[waitlist] Added user {telegram_user_id} to VIP waitlist")
    except Exception as exc:
        logger.warning(f"[waitlist] Could not add {telegram_user_id}: {exc}")


async def _apply_referral_bonus(event: Dict[str, Any]) -> None:
    """Grant +7 days to the referrer when a referred user pays.

    Looks up ``referred_by`` on the paying user and extends the referrer's
    active subscription by 7 days (or adds 7 days to their PREMIUM tier).
    """
    if not is_db_configured():
        return
    REFERRAL_BONUS_DAYS = int(os.getenv("REFERRAL_BONUS_DAYS", "7"))
    try:
        data = event.get("data") or {}
        meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}
        buyer_id = int(meta.get("telegram_user_id") or meta.get("user_id") or 0)
        if not buyer_id:
            return

        from sqlalchemy import select
        from db.models import User

        async with get_session() as session:
            buyer_row = await session.execute(
                select(User).where(User.telegram_user_id == buyer_id)
            )
            buyer = buyer_row.scalars().first()
            if not buyer or not getattr(buyer, "referred_by", None):
                return

            referrer_id = int(buyer.referred_by)
            referrer_row = await session.execute(
                select(User).where(User.telegram_user_id == referrer_id)
            )
            referrer = referrer_row.scalars().first()
            if not referrer:
                return

            tier_to_extend = "vip" if str(getattr(referrer, "tier", "") or "").strip().lower() == "vip" else "premium"
            reference = str(data.get("reference") or "").strip() or f"buyer-{buyer_id}"
            reward_ref = f"REFERRAL_PAY:{referrer_id}:{reference}"[:120]
            await activate_subscription(
                session=session,
                telegram_user_id=referrer_id,
                tier=tier_to_extend,
                duration_days=int(REFERRAL_BONUS_DAYS),
                paystack_reference=reward_ref,
                meta={
                    "source": "referral_payment_bonus",
                    "buyer_id": int(buyer_id),
                    "reference": reference,
                    "grant_days": int(REFERRAL_BONUS_DAYS),
                },
            )
            session.add(
                ReferralReward(
                    referrer_user_id=int(referrer.id),
                    referred_user_id=int(buyer.id),
                    reward_type="premium_days_payment",
                    reward_value=int(REFERRAL_BONUS_DAYS),
                )
            )
            await session.commit()
            logger.info(
                "[referral] Granted +%s days to referrer %s (buyer=%s reference=%s tier=%s)",
                REFERRAL_BONUS_DAYS,
                referrer_id,
                buyer_id,
                reference,
                tier_to_extend,
            )
    except Exception as exc:
        logger.warning(f"[referral] _apply_referral_bonus failed: {exc}")


async def _handle_charge_success_recurring(
    event: Dict[str, Any],
    persisted: Dict[str, Any],
) -> None:
    """On every charge.success, save subscription/customer codes and send a
    renewal DM when the charge is an automatic monthly renewal (not first-time)."""
    if not is_db_configured():
        return
    try:
        data = event.get("data") or {}
        meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}
        telegram_user_id = int(meta.get("telegram_user_id") or meta.get("user_id") or 0)
        if not telegram_user_id:
            return

        subscription_code = str(data.get("subscription_code") or "").strip() or None
        customer_code = str((data.get("customer") or {}).get("customer_code") or "").strip() or None
        tier = str(meta.get("tier") or "premium").strip().lower()

        from sqlalchemy import select, update as sa_update
        from db.models import User

        async with get_session() as session:
            row = await session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
            user = row.scalars().first()
            if not user:
                return

            # Renewal = user already had a subscription code on file
            is_renewal = bool(getattr(user, "paystack_subscription_code", None))

            update_vals: Dict[str, Any] = {"auto_renew": True}
            if subscription_code:
                update_vals["paystack_subscription_code"] = subscription_code
            if customer_code:
                update_vals["paystack_customer_code"] = customer_code
            await session.execute(
                sa_update(User).where(User.id == user.id).values(**update_vals)
            )
            await session.commit()

        if is_renewal:
            await _send_telegram_dm(
                telegram_user_id,
                f"\u2705 *Payment Successful!*\n\n"
                f"Your {tier.upper()} subscription has automatically renewed. "
                f"You are good for another 30 days. Let's catch these pips! \U0001f680",
            )
    except Exception as exc:
        logger.warning(f"[recurring] _handle_charge_success_recurring failed: {exc}")


async def _handle_payment_failed(event: Dict[str, Any]) -> None:
    """Handle invoice.payment_failed: downgrade to FREE, clear auto_renew, send DM."""
    if not is_db_configured():
        return
    try:
        data = event.get("data") or {}
        meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}
        telegram_user_id_raw = meta.get("telegram_user_id") or meta.get("user_id")

        # Fallback: resolve via subscription_code if metadata is missing
        if not telegram_user_id_raw:
            sub_code = str(
                (data.get("subscription") or {}).get("subscription_code")
                or data.get("subscription_code")
                or ""
            ).strip()
            if sub_code:
                from sqlalchemy import select
                from db.models import User
                async with get_session() as session:
                    row = await session.execute(
                        select(User).where(User.paystack_subscription_code == sub_code)
                    )
                    found = row.scalars().first()
                    if found:
                        telegram_user_id_raw = found.telegram_user_id

        if not telegram_user_id_raw:
            logger.warning("[payment_failed] Cannot resolve user from event")
            return

        telegram_user_id = int(telegram_user_id_raw)

        from sqlalchemy import select, update as sa_update
        from db.models import User

        was_vip = False
        async with get_session() as session:
            row = await session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
            user = row.scalars().first()
            if not user:
                return
            was_vip = getattr(user, "tier", "free").lower() == "vip"
            await session.execute(
                sa_update(User)
                .where(User.id == user.id)
                .values(tier="free", auto_renew=False)
            )
            await session.commit()

        logger.info(
            f"[payment_failed] Downgraded user {telegram_user_id} to free "
            f"(was_vip={was_vip})"
        )

        upgrade_url = os.getenv(
            "PAYSTACK_CALLBACK_URL", "https://t.me/SignalRankAIBot"
        )
        await _send_telegram_dm(
            telegram_user_id,
            f"\u26a0\ufe0f *Payment Failed*\n\n"
            f"We couldn't process your automatic renewal. "
            f"Your access has been downgraded to FREE.\n\n"
            f"[\U0001f4b3 Click here to update your card and restore your access.]({upgrade_url})",
        )
    except Exception as exc:
        logger.warning(f"[payment_failed] _handle_payment_failed failed: {exc}")


async def create_paystack_checkout(
    telegram_user_id: int,
    tier: str,
    amount_ngn: int,
    email: str = "user@signalrank.ai",
    duration_days: int = 30,
    referral_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Call Paystack /transaction/initialize and return the checkout URL.

    Args:
        telegram_user_id: The buyer's Telegram user ID.
        tier:             "premium" or "vip".
        amount_ngn:       Price in Nigerian Naira (converted to kobo internally).
        email:            Customer email (required by Paystack).
        duration_days:    Subscription length in days.
        referral_code:    Optional referrer telegram_user_id (for bonus tracking).

    Returns:
        ``{"url": str, "reference": str}`` on success.
        ``{"error": str}`` on failure.
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return {"error": "PAYSTACK_SECRET_KEY not configured"}

    amount_kobo = amount_ngn * 100
    import uuid

    reference = f"sr-{tier.lower()}-{telegram_user_id}-{uuid.uuid4().hex[:8]}"

    # Recurring plan code — configure PAYSTACK_PREMIUM_PLAN_CODE / PAYSTACK_VIP_PLAN_CODE
    # in the environment after creating plans in the Paystack dashboard.
    plan_code = os.getenv(f"PAYSTACK_{tier.upper()}_PLAN_CODE", "").strip()

    payload: Dict[str, Any] = {
        "email": email,
        "reference": reference,
        "currency": "NGN",
        "metadata": {
            "telegram_user_id": telegram_user_id,
            "tier": tier.lower(),
            "duration_days": duration_days,
            "referral_code": referral_code,
        },
        "callback_url": os.getenv("PAYSTACK_CALLBACK_URL", ""),
    }
    if plan_code:
        # Recurring: Paystack manages the billing amount from the plan definition
        payload["plan"] = plan_code
    else:
        # One-off: pass explicit amount in kobo
        payload["amount"] = amount_kobo
    headers = {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") and data.get("data"):
            return {
                "url": data["data"]["authorization_url"],
                "reference": data["data"]["reference"],
            }
        return {"error": data.get("message", "Paystack init failed")}
    except Exception as exc:
        logger.error(f"[paystack_checkout] {exc}")
        return {"error": str(exc)}


@app.post("/upgrade")
async def upgrade_endpoint(request: Request) -> JSONResponse:
    """Generate a dynamic Paystack checkout link for tier upgrades.

    Body (JSON):
        telegram_user_id: int  (required)
        tier:             str  "premium" | "vip"
        email:            str  (optional)
        referral_code:    str  (optional)

    Returns:
        200: {"checkout_url": str, "reference": str}
        409: VIP full → add to waitlist
    """
    body = await request.json()
    uid: int = int(body.get("telegram_user_id") or 0)
    tier: str = str(body.get("tier") or "premium").lower().strip()
    email: str = str(body.get("email") or f"user{uid}@signalrank.ai")
    referral_code: Optional[str] = body.get("referral_code")

    if not uid:
        raise HTTPException(status_code=400, detail="telegram_user_id required")
    if tier not in ("premium", "vip"):
        raise HTTPException(status_code=400, detail="tier must be 'premium' or 'vip'")

    PRICES: Dict[str, int] = {
        "premium": int(os.getenv("PREMIUM_PRICE_NGN", "15000")),
        "vip": int(os.getenv("VIP_PRICE_NGN", "30000")),
    }

    # VIP capacity check
    if tier == "vip" and ENGINE is not None:
        vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15"))
        try:
            from core.redis_state import state as _state

            exclude_ids = set()
            try:
                from config import config as _cfg  # type: ignore

                exclude_ids = set(getattr(_cfg, "OWNER_IDS", set()) or set())
            except Exception:
                pass
            async with get_session() as session:
                active_sub = await get_active_subscription(session, telegram_user_id=uid, tier="vip")
                if active_sub is None:
                    used = await count_active_vip_users(session, exclude_telegram_user_ids=exclude_ids)
                    if used >= vip_limit and uid not in exclude_ids:
                        await _add_to_vip_waitlist(uid)
                        return JSONResponse(
                            status_code=409,
                            content={
                                "error": "VIP is full",
                                "waitlist": True,
                                "message": (
                                    "VIP is currently full. You've been added to the waitlist "
                                    "and will be notified when a seat opens."
                                ),
                            },
                        )
        except Exception as exc:
            logger.warning(f"[upgrade] VIP capacity check failed: {exc}")

    result = await create_paystack_checkout(
        telegram_user_id=uid,
        tier=tier,
        amount_ngn=PRICES[tier],
        email=email,
        duration_days=30,
        referral_code=referral_code,
    )
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return JSONResponse({"checkout_url": result["url"], "reference": result["reference"]})
