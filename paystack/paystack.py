
import requests
from payments.models import WEEKLY_PLAN
import os
import hmac
import hashlib
import logging
from db.database import set_subscription


PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET')
PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/'

# Setup audit logger
logging.basicConfig(filename='audit.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

AMOUNTS = {
    # Recommended pricing (Nigeria-optimized)
    'PREMIUM_MONTHLY': 5000,
    'PREMIUM_QUARTERLY': 12000,
    'PREMIUM_SEMIANNUAL': 20000,
    'VIP_MONTHLY': 20000,

    # Legacy/optional weekly pricing (kept for backward compatibility)
    'PREMIUM_WEEKLY': 3000,
    'VIP_WEEKLY': 8000,
    'WEEKLY_PLAN': WEEKLY_PLAN['price_ngn']
}
DURATIONS = {
    'PREMIUM_MONTHLY': 30,
    'PREMIUM_QUARTERLY': 90,
    'PREMIUM_SEMIANNUAL': 180,
    'PREMIUM_WEEKLY': 7,
    'VIP_MONTHLY': 30,
    'VIP_WEEKLY': 7,
    'WEEKLY_PLAN': WEEKLY_PLAN['duration_days']
}

def verify_payment(reference, user_id):
    from db.database import approve_extra_signals
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
    response = requests.get(PAYSTACK_VERIFY_URL + reference, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['data']['status'] == 'success':
            amount = int(data['data']['amount']) // 100  # Paystack returns kobo
            metadata = data['data'].get('metadata', {})
            if not metadata or not isinstance(metadata, dict):
                logging.warning(f"Payment missing metadata: user {user_id}, amount {amount}")
                return False, "❌ Payment missing required metadata. Please use the official payment link.", None
            # Extra signal purchase
            if metadata.get('duration') == 'EXTRA':
                extra_count = int(metadata.get('extra_count', 1))
                tier = metadata.get('tier', 'PREMIUM')
                expected_price = 300 * extra_count if tier == 'PREMIUM' else 500 * extra_count
                if amount != expected_price:
                    logging.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for extra {tier}")
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your extra signal purchase.", None
                approve_extra_signals(user_id, extra_count)
                logging.info(f"Extra signals credited: user {user_id}, tier {tier}, count {extra_count}")
                return True, f"✅ Payment verified! {extra_count} extra {tier.title()} signal(s) credited for today.", tier
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
                    logging.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for {key}")
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your subscription.", None
                set_subscription(user_id, key, expected_days, reference)
                logging.info(f"Subscription activated: user {user_id}, tier {key}, duration {expected_days}")
                return True, f"✅ Payment verified! Weekly Plan access granted.", key
            if not tier or (not duration and duration_days is None):
                logging.warning(f"Subscription payment missing tier/duration: user {user_id}, amount {amount}")
                return False, "❌ Payment missing required subscription details. Please use the official payment link.", None

            # New path: tier in {premium,vip} with explicit duration_days
            if duration_days is not None and str(tier).strip().lower() in {"premium", "vip"}:
                from db.database import set_subscription, count_active_vip_seats
                days = int(duration_days)
                tnorm = str(tier).strip().upper()
                if tnorm == "VIP":
                    used, remaining, limit = count_active_vip_seats()
                    # Excludes owner/bypassed by definition; allow if the payer is already VIP (renewal).
                    from db.database import get_subscription
                    sub = get_subscription(user_id)
                    already_vip = bool(sub and not sub.get('expired', True) and str(sub.get('tier', '')).upper().startswith('VIP'))
                    if not already_vip and remaining <= 0:
                        return False, f"❌ VIP is currently full ({limit} seats). Please try again later.", None
                # Amount check for recommended plans
                if tnorm == "PREMIUM" and amount not in {5000, 12000, 20000}:
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund.", None
                if tnorm == "VIP" and amount != 20000:
                    return False, f"❌ Wrong amount paid ({amount}₦). No refund.", None
                key = f"{tnorm}_DAYS_{days}"
                set_subscription(user_id, key, days, reference)
                logging.info(f"Subscription activated: user {user_id}, tier {key}, duration {days}")
                return True, f"✅ Payment verified! {tnorm.title()} access granted.", key
            # Block repeat first-time VIP trial
            if tier.upper() == 'VIP' and duration.lower() == 'trial':
                from db.database import has_ever_had_vip
                if has_ever_had_vip(user_id):
                    logging.warning(f"Repeat VIP trial attempt: user {user_id}")
                    return False, "❌ VIP trial is only available once per user. Please choose a regular VIP plan.", None
            # Validate amount for subscription
            key = f"{tier.upper()}_{duration.upper()}"
            expected_price = AMOUNTS.get(key)
            expected_days = DURATIONS.get(key)
            if expected_price is None or expected_days is None or amount != expected_price:
                logging.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for {key}")
                return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your subscription.", None

            # VIP seat cap (legacy path)
            if key.startswith("VIP"):
                from db.database import count_active_vip_seats, get_subscription
                used, remaining, limit = count_active_vip_seats()
                sub = get_subscription(user_id)
                already_vip = bool(sub and not sub.get('expired', True) and str(sub.get('tier', '')).upper().startswith('VIP'))
                if not already_vip and remaining <= 0:
                    return False, f"❌ VIP is currently full ({limit} seats). Please try again later.", None
            set_subscription(user_id, key, expected_days, reference)
            logging.info(f"Subscription activated: user {user_id}, tier {key}, duration {expected_days}")
            return True, f"✅ Payment verified! {tier.title()} {duration.title()} access granted.", key
    return False, "❌ Payment not verified. Please try again.", None

def match_amount_to_tier(amount):
    for k, v in AMOUNTS.items():
        if amount == v:
            return k
    return None

# --- Webhook signature verification ---
def verify_webhook_signature(request_body, signature):
    computed = hmac.new(PAYSTACK_WEBHOOK_SECRET.encode(), request_body, hashlib.sha512).hexdigest()
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
    # Compose metadata for Paystack payment
    metadata = {
        # Prefer field names used by the FastAPI webhook extractor.
        "telegram_user_id": user_id
    }
    if plan_code:
        metadata["plan_code"] = str(plan_code)
    if plan_name == "Weekly Plan":
        metadata["tier"] = "WEEKLY_PLAN"
        metadata["duration"] = "WEEKLY"
        metadata["duration_days"] = DURATIONS.get("WEEKLY_PLAN")
    elif extra_count:
        metadata["tier"] = tier or "PREMIUM"
        metadata["duration"] = "EXTRA"
        metadata["extra_count"] = extra_count
    elif tier and (duration or duration_days):
        metadata["tier"] = tier
        if duration:
            metadata["duration"] = duration
        if duration_days is not None:
            metadata["duration_days"] = int(duration_days)
    # In production, use Paystack API to create a payment session with metadata
    # For now, encode metadata in query params for testing
    import urllib.parse
    meta_str = urllib.parse.quote(str(metadata))
    return f"https://paystack.com/pay/signalrankai?user={user_id}&price={price}&metadata={meta_str}"
