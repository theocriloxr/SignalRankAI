import requests
import os

PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'YOUR_PAYSTACK_SECRET_KEY')

PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/'

# Example: verify a payment

def verify_payment(reference):
    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }
    response = requests.get(PAYSTACK_VERIFY_URL + reference, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data['data']['status'] == 'success':
            return True, data['data']
    return False, None

# Example: check subscription status (to be expanded)
def is_user_subscribed(user_id):
    # Placeholder: check DB or Paystack for active subscription
    return False
