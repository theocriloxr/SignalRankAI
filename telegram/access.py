from payments.subscriptions import get_subscription
from config import OWNER_IDS

def resolve_user_tier(user_id):
    if user_id in OWNER_IDS:
        return "OWNER"
    sub = get_subscription(user_id)
    if not sub or not sub.is_active():
        return "FREE"
    return sub.tier
