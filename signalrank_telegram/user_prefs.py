# user_prefs.py
"""
User Notification Preferences Store
Stores per-user notification preferences for assets, timeframes, and strategies.
"""
import threading
from collections import defaultdict

class UserPrefsStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.prefs = defaultdict(dict)  # user_id -> { 'assets': set, 'timeframes': set, 'strategies': set }

    def set_prefs(self, user_id, assets=None, timeframes=None, strategies=None, **extra):
        """Store non-trading UI preferences only.

        Trading filters are durable in ``services.user_intelligence``. This
        compatibility store remains for UI-only values such as language and
        must accept those named fields without raising ``TypeError``.
        """
        with self.lock:
            if assets is not None:
                self.prefs[user_id]['assets'] = set(assets)
            if timeframes is not None:
                self.prefs[user_id]['timeframes'] = set(timeframes)
            if strategies is not None:
                self.prefs[user_id]['strategies'] = set(strategies)
            for key, value in extra.items():
                self.prefs[user_id][str(key)] = value

    def get_prefs(self, user_id):
        with self.lock:
            return dict(self.prefs.get(user_id, {}))

    def clear_prefs(self, user_id):
        with self.lock:
            self.prefs.pop(user_id, None)

user_prefs_store = UserPrefsStore()
