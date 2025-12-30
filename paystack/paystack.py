
import requests
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
    'PREMIUM_MONTHLY': 10000,
    'PREMIUM_WEEKLY': 3000,
    'VIP_MONTHLY': 25000,
    'VIP_WEEKLY': 8000
}
DURATIONS = {
    'PREMIUM_MONTHLY': 30,
    'PREMIUM_WEEKLY': 7,
    'VIP_MONTHLY': 30,
    'VIP_WEEKLY': 7
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
            if not tier or not duration:
                logging.warning(f"Subscription payment missing tier/duration: user {user_id}, amount {amount}")
                return False, "❌ Payment missing required subscription details. Please use the official payment link.", None
            # Validate amount for subscription
            key = f"{tier.upper()}_{duration.upper()}"
            expected_price = AMOUNTS.get(key)
            expected_days = DURATIONS.get(key)
            if expected_price is None or expected_days is None or amount != expected_price:
                logging.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount} for {key}")
                return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your subscription.", None
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
def generate_paystack_link(user_id, price, tier=None, duration=None, extra_count=None):
    # Compose metadata for Paystack payment
    metadata = {
        "telegram_id": user_id
    }
    if extra_count:
        metadata["tier"] = tier or "PREMIUM"
        metadata["duration"] = "EXTRA"
        metadata["extra_count"] = extra_count
    elif tier and duration:
        metadata["tier"] = tier
        metadata["duration"] = duration
    # In production, use Paystack API to create a payment session with metadata
    # For now, encode metadata in query params for testing
    import urllib.parse
    meta_str = urllib.parse.quote(str(metadata))
    return f"https://paystack.com/pay/signalrankai?user={user_id}&price={price}&metadata={meta_str}"
