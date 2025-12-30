from datetime import datetime

class Subscription:
    def __init__(self, user_id, tier, expires_at):
        self.user_id = user_id
        self.tier = tier
        self.expires_at = expires_at

    def is_active(self):
        return datetime.utcnow() < self.expires_at
    # --- Region-Optimized Weekly Plan ---
    WEEKLY_PLAN = {
        'name': 'Weekly Plan',
        'price_ngn': 1500,  # Example: ₦1500 per week
        'duration_days': 7,
        'features': [
            'Full access to all signals',
            'Priority support',
            'Region-optimized for Nigeria/West Africa',
        ]
    }
