import hmac
import hashlib
import os
import json

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

def verify_signature(payload, signature):
    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

def handle_webhook(request):
    signature = request.headers.get("x-paystack-signature")
    payload = request.body
    if not verify_signature(payload, signature):
        raise Exception("Invalid Paystack signature")
    event = json.loads(payload)
    process_event(event)

# You must implement process_event(event) to handle subscription activation
