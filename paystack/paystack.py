
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
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
    response = requests.get(PAYSTACK_VERIFY_URL + reference, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['data']['status'] == 'success':
            amount = int(data['data']['amount']) // 100  # Paystack returns kobo
            tier, duration = match_amount_to_tier(amount)
            if not tier:
                logging.warning(f"Fraud attempt: user {user_id} paid wrong amount {amount}")
                return False, f"❌ Wrong amount paid ({amount}₦). No refund. Please pay the exact amount for your tier.", None
            set_subscription(user_id, tier, duration, reference)
            logging.info(f"Subscription activated: user {user_id}, tier {tier}, duration {duration}")
            return True, f"✅ Payment verified! {tier.replace('_',' ').title()} access granted.", tier
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
def generate_paystack_link(user_id, price, extra_count=1):
    # Dummy link for testing
    return f"https://paystack.com/pay/signalrankai?user={user_id}&price={price}&extra={extra_count}"
