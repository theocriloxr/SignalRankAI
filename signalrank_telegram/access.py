from db.database import get_subscription
from config import OWNER_IDS

def resolve_user_tier(user_id):
    if user_id in OWNER_IDS:
        return "OWNER"
    sub = get_subscription(user_id)
    if sub is None or sub.get('expired', True):
        return "FREE"
    if sub.get('bypass_key_used'):
        return "OWNER"
    return sub.get('tier', 'FREE')