
import asyncio
import os
import hmac
import hashlib
import logging
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any, Mapping

import httpx

from payments.models import WEEKLY_PLAN
from config import config
PAYSTACK_SECRET_KEY: str | None = config.PAYSTACK_SECRET_KEY
PAYSTACK_WEBHOOK_SECRET: str | None = config.PAYSTACK_WEBHOOK_SECRET
PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/'
PAYSTACK_INIT_URL = 'https://api.paystack.co/transaction/initialize'

_audit_logger: logging.Logger = logging.getLogger("audit")

AMOUNTS = {
    # Environment-backed production catalog.
    'PREMIUM_WEEKLY': int(os.getenv('PREMIUM_WEEKLY_PRICE_NGN', '8000') or 8000),
    'PREMIUM_MONTHLY': int(os.getenv('PREMIUM_MONTHLY_PRICE_NGN', '24000') or 24000),
    'PREMIUM_QUARTERLY': int(os.getenv('PREMIUM_QUARTERLY_PRICE_NGN', '56000') or 56000),
    'PREMIUM_YEARLY': int(os.getenv('PREMIUM_YEARLY_PRICE_NGN', '192000') or 192000),
    'VIP_MONTHLY': int(os.getenv('VIP_MONTHLY_PRICE_NGN', os.getenv('VIP_PRICE_NGN', '40000')) or 40000),
    'VIP_WEEKLY': int(os.getenv('VIP_WEEKLY_PRICE_NGN', '16000') or 16000),
    'WEEKLY_PLAN': WEEKLY_PLAN['price_ngn'],
}

DURATIONS = {
    'PREMIUM_WEEKLY': 7,
    'PREMIUM_MONTHLY': 30,
    'PREMIUM_QUARTERLY': 90,
    'PREMIUM_YEARLY': 365,
    'VIP_MONTHLY': 30,
    'VIP_WEEKLY': 7,
    'WEEKLY_PLAN': WEEKLY_PLAN['duration_days']
}

def is_valid_paystack_checkout_url(value: object) -> bool:
    if not isinstance(value, str):
        return False

    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False

    hostname = str(parsed.hostname or "").lower()

    return (
        parsed.scheme == "https"
        and (
            hostname == "paystack.com"
            or hostname.endswith(".paystack.com")
        )
    )

def verify_payment(reference, user_id):
    from core.redis_state import state
    headers: dict[str, str] = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
    response: requests.Response = requests.get(PAYSTACK_VERIFY_URL + reference, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['data']['status'] == 'success':
            amount: int = int(data['data']['amount']) // 100  # Paystack returns kobo
            metadata = data['data'].get('metadata', {})
            if not metadata or not isinstance(metadata, dict):
                _audit_logger.warning(f"Payment missing metadata: user {user_id}, amount {amount}")
                return False, "❌ Payment missing required metadata. Please use the official payment link.", None
            # Extra signal purchase
            if metadata.get('duration') == 'EXTRA':
                extra_count = int(metadata.get('extra_count', 1))
                expected_price: int = 600 * extra_count
                if amount != expected_price:
                    _audit_logger.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for extra_signals")
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your extra signal purchase.", None
                try:
                    state.add_extra_signals_sync(int(user_id), int(extra_count), ttl_seconds=86400)
                except Exception:
                    pass
                _audit_logger.info(f"Extra signals credited: user {user_id}, count {extra_count}")
                return True, f"✅ Payment verified! {extra_count} extra signal(s) credited (24h access).", "EXTRA_SIGNALS"
            # Subscription purchase
            tier = metadata.get('tier')
            duration = metadata.get('duration')
            duration_days = metadata.get('duration_days')
            # Support region-optimized weekly plan
            if tier == 'WEEKLY_PLAN' or (tier and duration and tier.upper() == 'WEEKLY_PLAN'):
                key = 'WEEKLY_PLAN'
                expected_price = AMOUNTS.get(key)
                expected_days = DURATIONS.get(key)
                if amount != expected_price:
                    _audit_logger.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for {key}")
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your subscription.", None
                # Manual verify flow is deprecated; webhook persistence is the source of truth.
                return False, "❌ Manual verification is no longer supported. Please wait for webhook confirmation.", None
            if not tier or (not duration and duration_days is None):
                _audit_logger.warning(f"Subscription payment missing tier/duration: user {user_id}, amount {amount}")
                return False, "❌ Payment missing required subscription details. Please use the official payment link.", None

            # New path: tier in {premium,vip} with explicit duration_days
            if duration_days is not None and str(tier).strip().lower() in {"premium", "vip"}:
                days = int(duration_days)
                tnorm: str = str(tier).strip().upper()
                if tnorm == "VIP":
                    pass
                # Amount check for recommended plans
                if tnorm == "PREMIUM" and amount not in {AMOUNTS["PREMIUM_WEEKLY"], AMOUNTS["PREMIUM_MONTHLY"], AMOUNTS["PREMIUM_QUARTERLY"], AMOUNTS["PREMIUM_YEARLY"]}:
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund.", None
                if tnorm == "VIP" and amount != AMOUNTS["VIP_MONTHLY"]:
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund.", None
                return False, "❌ Manual verification is no longer supported. Please wait for webhook confirmation.", None
            # Block repeat first-time VIP trial
            if tier.upper() == 'VIP' and duration.lower() == 'trial':
                return False, "❌ VIP trials are not supported via manual verification.", None
            # Validate amount for subscription
            key: str = f"{tier.upper()}_{duration.upper()}"
            expected_price = AMOUNTS.get(key)
            expected_days = DURATIONS.get(key)
            if expected_price is None or expected_days is None or amount != expected_price:
                _audit_logger.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for {key}")
                return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your subscription.", None

            # VIP seat cap (legacy path)
            if key.startswith("VIP"):
                return False, "❌ VIP seat checks require webhook-based activation.", None
            return False, "❌ Manual verification is no longer supported. Please wait for webhook confirmation.", None
    return False, "❌ Payment not verified. Please try again.", None

def match_amount_to_tier(amount) -> str | None:
    for k, v in AMOUNTS.items():
        if amount == v:
            return k
    return None

# --- Webhook signature verification ---
def verify_webhook_signature(request_body: bytes | str, signature: str | None) -> bool:
    from payments.paystack_policy import verify_paystack_event_signature
    return verify_paystack_event_signature(request_body, signature)

# --- STUB FOR TELEGRAM BOT ---
@dataclass(frozen=True)
class CheckoutInitializationResult:
    """Type-safe result of a checkout initialization.

    ``ok=True`` means ``authorization_url`` is a validated Paystack HTTPS
    checkout URL. A blocked policy or failed init returns ``ok=False`` with a
    machine-readable ``reason`` — never a sentence disguised as a URL.
    """

    ok: bool
    authorization_url: str | None = None
    reference: str | None = None
    mode: str = "unknown"
    reason: str | None = None


def _new_reference() -> str:
    """Server-side reference: never supplied by the browser."""
    return f"sra-{uuid.uuid4().hex[:24]}"


async def initialize_paystack_checkout(
    telegram_user_id: int,
    plan_code: str,
    *,
    email: str | None = None,
    extra_count: int | None = None,
    environ: Mapping[str, str] | None = None,
) -> CheckoutInitializationResult:
    """Initialize exactly one Paystack checkout for a validated plan.

    The plan price is read from the authoritative catalogue (never from the
    client). A pending checkout row is persisted *before* the Paystack URL is
    returned so the webhook can later require the stored reference/plan.
    """
    from payments.plan_catalogue import get_plan
    from payments.payment_config import resolve_paystack_configuration

    env = environ if environ is not None else os.environ
    plan = get_plan(plan_code, env)
    if plan is None:
        return CheckoutInitializationResult(False, mode="unknown", reason="unknown_plan_code")

    cfg = resolve_paystack_configuration(env)
    if not cfg.checkout_policy_allowed:
        logging.info(
            "[paystack_checkout_policy] allowed=false mode=%s reason=%s plan=%s user=%s",
            cfg.key_mode, cfg.checkout_policy_reason, plan.code, telegram_user_id,
        )
        return CheckoutInitializationResult(
            False, mode=cfg.key_mode, reason=cfg.checkout_policy_reason or "checkout_policy_blocked",
        )

    from payments.paystack_policy import evaluate_paystack_operation
    policy = evaluate_paystack_operation(
        telegram_user_id=int(telegram_user_id),
        amount_ngn=float(plan.price_ngn),
        environ=env,
    )
    if not policy.allowed:
        logging.warning(
            "[paystack_checkout_policy] blocked user=%s plan=%s amount=%s mode=%s reason=%s",
            telegram_user_id, plan.code, plan.price_ngn, policy.mode, policy.reason,
        )
        return CheckoutInitializationResult(False, mode=policy.mode, reason=policy.reason)

    secret: str | None = str(env.get("PAYSTACK_SECRET_KEY") or "").strip() or None
    if not secret:
        return CheckoutInitializationResult(False, mode=cfg.key_mode, reason="paystack_secret_missing")

    # Amount conversion happens exactly once, here, in kobo.
    amount_kobo: int = plan.price_kobo()
    reference: str = _new_reference()

    metadata: dict[str, Any] = {
        "telegram_user_id": int(telegram_user_id),
        "plan_code": plan.code,
        "tier": plan.tier,
        "duration": plan.duration,
        "duration_days": int(plan.duration_days),
        "amount_ngn": int(plan.price_ngn),
        "paystack_mode": policy.mode,
        "guarded_staging_live": policy.reason == "guarded_live_staging",
    }
    if extra_count:
        metadata["duration"] = "EXTRA"
        metadata["extra_count"] = int(extra_count)

    # Persist the pending checkout before exposing the URL to the user. The
    # webhook requires this stored reference and intended plan for activation.
    try:
        from db.pg_features import record_payment_event
        from db.session import get_session
        async with get_session(label="paystack.checkout.pending", timeout_seconds=8.0) as session:
            await record_payment_event(
                session,
                telegram_user_id=int(telegram_user_id),
                paystack_reference=reference,
                amount_ngn=int(plan.price_ngn),
                currency="NGN",
                kind="checkout_pending",
                tier=str(plan.tier).lower(),
                duration_days=int(plan.duration_days),
                plan_code=plan.code,
                meta={"status": "pending", "mode": policy.mode},
            )
            await session.commit()
        logging.info(
            "[paystack_checkout_initialize_started] user=%s plan=%s reference=%s mode=%s",
            telegram_user_id, plan.code, reference, policy.mode,
        )
    except Exception as exc:
        logging.warning(
            "[paystack_checkout_pending_persist_failed] user=%s plan=%s err=%s",
            telegram_user_id, plan.code, type(exc).__name__,
        )
        return CheckoutInitializationResult(False, mode=policy.mode, reason="pending_checkout_persist_failed")

    resolved_email = str(email or "").strip() or f"user{int(telegram_user_id)}@signalrank.ai"
    payload: dict[str, Any] = {
        "email": resolved_email,
        "amount": int(amount_kobo),
        "reference": reference,
        "metadata": metadata,
    }

    callback_url: str | None = env.get("PAYSTACK_CALLBACK_URL") or env.get("PUBLIC_BASE_URL")
    if callback_url:
        payload["callback_url"] = callback_url

    headers: dict[str, str] = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(PAYSTACK_INIT_URL, json=payload, headers=headers)
            data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not bool(data.get("status")):
            logging.warning(
                "[paystack_checkout_initialize_failed] status=%s user=%s plan=%s reference=%s",
                resp.status_code, telegram_user_id, plan.code, reference,
            )
            return CheckoutInitializationResult(False, reference=reference, mode=policy.mode, reason="paystack_init_failed")
        auth_url = str(((data.get("data") or {}).get("authorization_url") or "")).strip()
        if not is_valid_paystack_checkout_url(auth_url):
            logging.error(
                "[paystack_checkout_initialize_failed] invalid_url user=%s plan=%s reference=%s",
                telegram_user_id, plan.code, reference,
            )
            return CheckoutInitializationResult(False, reference=reference, mode=policy.mode, reason="invalid_checkout_url")
        logging.info(
            "[paystack_checkout_initialize_succeeded] user=%s plan=%s reference=%s mode=%s",
            telegram_user_id, plan.code, reference, policy.mode,
        )
        return CheckoutInitializationResult(True, authorization_url=auth_url, reference=reference, mode=policy.mode)
    except Exception as exc:
        logging.warning(
            "[paystack_checkout_initialize_failed] exception=%s user=%s plan=%s",
            type(exc).__name__, telegram_user_id, plan.code,
        )
        return CheckoutInitializationResult(False, reference=reference, mode=policy.mode, reason="paystack_init_exception")


def generate_paystack_link(
    user_id,
    price,
    tier=None,
    duration=None,
    duration_days=None,
    extra_count=None,
    plan_name=None,
    plan_code=None,
):
    """Legacy synchronous wrapper retained for compatibility.

    Returns a validated Paystack ``authorization_url`` string, or ``None`` on
    any failure. Never returns an error sentence in place of a URL.
    """
    code = str(plan_code or "").strip()
    if not code:
        # Map legacy tier/duration args onto a plan code when possible.
        code = f"{str(tier or '').lower()}_{str(duration or '').lower()}".strip("_") or ""

    async def _run() -> CheckoutInitializationResult:
        if code and code in {"premium_monthly", "premium_quarterly", "premium_yearly", "vip_monthly"}:
            return await initialize_paystack_checkout(
                int(user_id), code, extra_count=extra_count,
            )
        # Legacy flows: build metadata directly (extra signals / weekly plan).
        return await _legacy_initialize(user_id, price, tier, duration, duration_days, extra_count, plan_name, code)

    try:
        loop = asyncio.get_running_loop()
        result = asyncio.run_coroutine_threadsafe(_run(), loop).result(timeout=30)
    except RuntimeError:
        result = asyncio.run(_run())
    if result.ok:
        return result.authorization_url
    return None


async def _legacy_initialize(user_id, price, tier, duration, duration_days, extra_count, plan_name, plan_code) -> CheckoutInitializationResult:
    """Backend for legacy ``generate_paystack_link`` calls (weekly plan / extras)."""
    from payments.payment_config import resolve_paystack_configuration
    cfg = resolve_paystack_configuration()
    secret = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip() or None
    if not secret:
        return CheckoutInitializationResult(False, mode=cfg.key_mode, reason="paystack_secret_missing")
    amount_ngn = int(price)
    reference: str = _new_reference()
    metadata: dict[str, Any] = {
        "telegram_user_id": int(user_id),
        "amount_ngn": int(amount_ngn),
        "paystack_mode": cfg.key_mode,
    }
    if plan_name == "Weekly Plan":
        metadata["tier"] = "WEEKLY_PLAN"
        metadata["duration"] = "WEEKLY"
        metadata["duration_days"] = int(DURATIONS.get("WEEKLY_PLAN") or 7)
    elif extra_count:
        metadata["tier"] = (tier or "PREMIUM")
        metadata["duration"] = "EXTRA"
        metadata["extra_count"] = int(extra_count)
    elif tier and (duration or duration_days is not None):
        metadata["tier"] = tier
        if duration:
            metadata["duration"] = duration
        if duration_days is not None:
            metadata["duration_days"] = int(duration_days)
    amount_kobo: int = max(100, amount_ngn) * 100
    payload: dict[str, Any] = {
        "email": f"user{int(user_id)}@signalrank.ai",
        "amount": int(amount_kobo),
        "reference": reference,
        "metadata": metadata,
    }
    if plan_code:
        payload["plan"] = str(plan_code)
    callback_url: str | None = os.getenv("PAYSTACK_CALLBACK_URL") or os.getenv("PUBLIC_BASE_URL")
    if callback_url:
        payload["callback_url"] = callback_url
    headers: dict[str, str] = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(PAYSTACK_INIT_URL, json=payload, headers=headers)
            data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not bool(data.get("status")):
            return CheckoutInitializationResult(False, reference=reference, mode=cfg.key_mode, reason="paystack_init_failed")
        auth_url = str(((data.get("data") or {}).get("authorization_url") or "")).strip()
        if not is_valid_paystack_checkout_url(auth_url):
            return CheckoutInitializationResult(False, reference=reference, mode=cfg.key_mode, reason="invalid_checkout_url")
        return CheckoutInitializationResult(True, authorization_url=auth_url, reference=reference, mode=cfg.key_mode)
    except Exception as exc:
        logging.warning("Paystack init exception: %s", type(exc).__name__)
        return CheckoutInitializationResult(False, reference=reference, mode=cfg.key_mode, reason="paystack_init_exception")
