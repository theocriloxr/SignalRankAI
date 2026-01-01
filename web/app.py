import hashlib
import hmac
import os
import socket
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from db.session import ENGINE, get_session
from db.repository import activate_subscription, count_active_vip_users, get_active_subscription
from core.redis_state import state


APP_NAME = "SignalRankAI"

request_latency = Histogram(
    "signalrankai_http_request_latency_seconds",
    "HTTP request latency",
    labelnames=("path", "method", "status"),
)

webhook_failures = Counter(
    "signalrankai_paystack_webhook_failures_total",
    "Total Paystack webhook failures",
    labelnames=("reason",),
)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_paystack_signature(raw_body: bytes, signature_header: Optional[str]) -> None:
    secret = os.getenv("PAYSTACK_WEBHOOK_SECRET") or os.getenv("PAYSTACK_SECRET_KEY")
    if not secret:
        webhook_failures.labels(reason="missing_secret").inc()
        raise HTTPException(status_code=500, detail="Paystack secret not configured")

    if not signature_header:
        webhook_failures.labels(reason="missing_signature").inc()
        raise HTTPException(status_code=400, detail="Missing x-paystack-signature")

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


def _extract_subscription_fields(event: Dict[str, Any]) -> Tuple[int, str, int, Optional[str], Dict[str, Any]]:
    data = event.get("data") or {}
    meta = (data.get("metadata") or {}) if isinstance(data, dict) else {}

    # Prefer explicit metadata fields set when generating the payment link.
    telegram_user_id = meta.get("telegram_user_id") or meta.get("user_id")
    tier = meta.get("tier") or meta.get("plan") or "free"
    duration_days = meta.get("duration_days") or meta.get("days") or 30
    reference = data.get("reference") if isinstance(data, dict) else None

    try:
        telegram_user_id_int = int(telegram_user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Missing telegram_user_id in metadata") from exc

    try:
        duration_days_int = int(duration_days)
    except Exception:
        duration_days_int = 30

    meta_out: Dict[str, Any] = {
        "raw_event": event.get("event"),
        "metadata": meta,
        "received_at": datetime.utcnow().isoformat() + "Z",
    }
    return telegram_user_id_int, str(tier), duration_days_int, reference, meta_out


async def _persist_subscription_if_configured(event: Dict[str, Any]) -> Dict[str, Any]:
    if ENGINE is None:
        return {"persisted": False, "reason": "DATABASE_URL not set"}

    try:
        telegram_user_id, tier, duration_days, reference, meta = _extract_subscription_fields(event)
    except HTTPException as exc:
        # Not all Paystack webhook events contain our subscription metadata.
        # If the signature is valid, acknowledge receipt and simply skip persistence.
        return {"persisted": False, "reason": str(getattr(exc, "detail", "unable_to_persist"))}
    async with get_session() as session:
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


app = FastAPI(title=APP_NAME, version="0.1.0")


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


@app.get("/health")
async def health() -> Dict[str, Any]:
    # Include non-sensitive deployment hints to verify which instance is serving traffic.
    return {
        "ok": True,
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


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


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
    await state.set_killswitch(enabled=enabled, reason=reason)
    ks = await state.get_killswitch()
    return {"enabled": ks.enabled, "reason": ks.reason, "updated_at": ks.updated_at}


@app.post("/webhooks/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(default=None, alias="x-paystack-signature"),
) -> JSONResponse:
    raw = await request.body()
    verify_paystack_signature(raw, x_paystack_signature)

    event = await request.json()
    confirmation = await confirm_paystack_event(event)
    if not confirmation.get("ok"):
        raise HTTPException(status_code=400, detail="Payment not verified")

    persisted = await _persist_subscription_if_configured(event)
    if persisted.get("persisted") is False and str(persisted.get("reason", "")).startswith("vip_full"):
        raise HTTPException(status_code=409, detail="VIP is currently full. Please try again later.")

    return JSONResponse(
        {
            "received": True,
            "verified": bool(confirmation.get("verified", False)),
            "persisted": persisted.get("persisted", False),
        }
    )
