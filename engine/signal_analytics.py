# signal_analytics.py
"""
Signal Quality Analytics Module
Tracks and logs signal delivery stats, fill rates, and user engagement for analytics and reporting.
"""
import threading
import time
from collections import defaultdict, Counter

class SignalAnalytics:
    def __init__(self):
        self.lock = threading.Lock()
        self.delivery_stats = Counter()
        self.fill_rates = defaultdict(list)  # symbol -> [filled, missed, ...]
        self.user_engagement = Counter()    # user_id -> count
        self.last_flush = time.time()

    def log_delivery(self, symbol, delivered=True):
        with self.lock:
            key = f"delivered_{symbol}" if delivered else f"missed_{symbol}"
            self.delivery_stats[key] += 1

    def log_fill(self, symbol, filled):
        with self.lock:
            self.fill_rates[symbol].append(filled)

    def log_user_engagement(self, user_id):
        with self.lock:
            self.user_engagement[user_id] += 1

    def get_stats(self):
        with self.lock:
            return {
                'delivery_stats': dict(self.delivery_stats),
                'fill_rates': {k: sum(v)/len(v) if v else 0 for k, v in self.fill_rates.items()},
                'user_engagement': dict(self.user_engagement),
            }

    def flush(self):
        """Flush analytics to logs and reset counters."""
        stats = self.get_stats()
        print("[analytics] Flushing stats:", stats, flush=True)
        self.last_flush = time.time()
        with self.lock:
            self.delivery_stats.clear()
            self.fill_rates.clear()
            self.user_engagement.clear()

# Singleton instance
signal_analytics = SignalAnalytics()
