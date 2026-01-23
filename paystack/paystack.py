
import requests
from payments.models import WEEKLY_PLAN
import os
import hmac
import hashlib
import logging


PAYSTACK_SECRET_KEY: str | None = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_WEBHOOK_SECRET: str | None = os.getenv('PAYSTACK_WEBHOOK_SECRET')
PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/'
PAYSTACK_INIT_URL = 'https://api.paystack.co/transaction/initialize'

_audit_logger: logging.Logger = logging.getLogger("audit")

AMOUNTS = {
    # Recommended pricing (Nigeria-optimized)
    'PREMIUM_WEEKLY': 4000,
    'PREMIUM_MONTHLY': 12000,
    'PREMIUM_QUARTERLY': 28000,
    'VIP_MONTHLY': 20000,

    # Legacy/optional weekly pricing (kept for backward compatibility)
    'VIP_WEEKLY': 8000,
    'WEEKLY_PLAN': WEEKLY_PLAN['price_ngn']
}
DURATIONS = {
    'PREMIUM_WEEKLY': 7,
    'PREMIUM_MONTHLY': 30,
    'PREMIUM_QUARTERLY': 90,
    'VIP_MONTHLY': 30,
    'VIP_WEEKLY': 7,
    'WEEKLY_PLAN': WEEKLY_PLAN['duration_days']
}

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
                expected_price: int = 300 * extra_count
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
                if tnorm == "PREMIUM" and amount not in {4000, 12000, 28000}:
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund.", None
                if tnorm == "VIP" and amount != 20000:
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
def verify_webhook_signature(request_body, signature) -> bool:
    secret: str | None = PAYSTACK_WEBHOOK_SECRET or PAYSTACK_SECRET_KEY
    if not secret:
        return False
    computed: str = hmac.new(secret.encode(), request_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature)

# --- STUB FOR TELEGRAM BOT ---
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
    """Create a Paystack checkout session and return a short, working URL.

    Uses Paystack Transaction Initialize API and returns `authorization_url`.
    Metadata fields are aligned with the FastAPI webhook extractor in web/app.py.
    """

    secret: str | None = os.getenv('PAYSTACK_SECRET_KEY')
    if not secret:
        # Fail closed: don't emit fake links.
        return "PAYSTACK_SECRET_KEY is not configured."

    amount_ngn = int(price)
    amount_kobo: int = max(100, amount_ngn) * 100

    metadata: dict[str, int] = {
        "telegram_user_id": int(user_id),
    }
    if plan_code:
        metadata["plan_code"] = str(plan_code)

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

    payload = {
        "email": f"user{int(user_id)}@signalrank.ai",
        "amount": int(amount_kobo),
        "metadata": metadata,
    }

    # Optional: set subscription plan code (Paystack will use it if enabled)
    if plan_code:
        payload["plan"] = str(plan_code)

    callback_url: str | None = os.getenv("PAYSTACK_CALLBACK_URL") or os.getenv("PUBLIC_BASE_URL")
    if callback_url:
        payload["callback_url"] = callback_url

    headers: dict[str, str] = {
        'Authorization': f'Bearer {secret}',
        'Content-Type': 'application/json',
    }

    try:
        resp: requests.Response = requests.post(PAYSTACK_INIT_URL, json=payload, headers=headers, timeout=20)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not bool(data.get('status')):
            logging.warning(f"Paystack init failed: status={resp.status_code} body={data}")
            return "Paystack checkout init failed. Please try again."
        auth_url = ((data.get('data') or {}).get('authorization_url') or '').strip()
        if not auth_url:
            return "Paystack did not return a checkout URL."
        return auth_url
    except Exception as exc:
        logging.warning(f"Paystack init exception: {exc}")
        return "Paystack checkout init error. Please try again."
