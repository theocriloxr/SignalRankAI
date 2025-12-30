from datetime import datetime

class Subscription:
    def __init__(self, user_id, tier, expires_at):
        self.user_id = user_id
        self.tier = tier
        self.expires_at = expires_at

    def is_active(self):
        return datetime.utcnow() < self.expires_at
