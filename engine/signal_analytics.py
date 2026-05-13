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


def calculate_volume_delta(candles: list[dict], window: int = 20) -> dict:
    """Calculate relative volume (RVOL) and signed volume delta for a candle series.

    Returns a dict with keys: 'rvol' (float), 'delta_ratio' (float), 'avg_volume' (float).
    - rvol: last_candle_volume / avg(previous window volumes)
    - delta_ratio: (sum_signed_volume_over_window) / (sum_volume_over_window)

    This helper is intentionally lightweight and avoids pandas to keep dependencies small.
    """
    try:
        if not candles or len(candles) < 2:
            return {"rvol": 0.0, "delta_ratio": 0.0, "avg_volume": 0.0}

        vols = [float(c.get("volume") or 0.0) for c in candles]
        opens = [float(c.get("open") or 0.0) for c in candles]
        closes = [float(c.get("close") or 0.0) for c in candles]

        last_vol = vols[-1]
        prev_window = vols[-(window + 1):-1] if len(vols) > 1 else []
        if not prev_window:
            avg_prev = float(sum(vols[:-1]) / max(1, len(vols[:-1]))) if len(vols) > 1 else 0.0
        else:
            avg_prev = float(sum(prev_window) / max(1, len(prev_window)))

        rvol = float(last_vol / avg_prev) if avg_prev > 0 else 0.0

        # Signed volume: treat bullish candle (close>open) as positive, bearish as negative
        signed = 0.0
        total = 0.0
        look = min(window, len(vols))
        for i in range(-look, 0):
            v = float(vols[i])
            o = float(opens[i])
            c = float(closes[i])
            total += v
            if c > o:
                signed += v
            elif c < o:
                signed -= v
            else:
                # neutral candle: no sign
                signed += 0.0

        delta_ratio = float(signed / total) if total > 0 else 0.0
        return {"rvol": float(rvol), "delta_ratio": float(delta_ratio), "avg_volume": float(avg_prev)}
    except Exception:
        return {"rvol": 0.0, "delta_ratio": 0.0, "avg_volume": 0.0}
