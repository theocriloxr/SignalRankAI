"""Shared tier constants and limits for signal delivery."""

from typing import Final

# Tier daily signal limits
TIER_DAILY_LIMITS: Final[dict[str, float]] = {
    "free": 3,
    "premium": float('inf'),
    "vip": float('inf'),
    "owner": float('inf'),
    "admin": float('inf'),
}

# Tier quality score thresholds
TIER_SCORE_THRESHOLDS: Final[dict[str, float]] = {
    "free": 80,
    "premium": 70,
    "vip": 70,
    "owner": 55,
    "admin": 55,
}

# Signal freshness: max age in seconds before signal is considered stale
# Values are intentionally generous — the live-price stale validator
# (validate_signal_freshness_sync / STALE_PRICE_THRESHOLD_PCT) is the
# primary gate; these age limits only catch genuinely ancient signals.
MAX_SIGNAL_AGE_SECONDS = {
    "crypto":    1800,   # 30 min  — crypto is 24/7, signals stay valid longer
    "fx":        3600,   # 60 min  — FX candles close on the hour
    "stock":     3600,   # 60 min  — intraday signals stay useful within session
    "commodity": 3600,   # 60 min  — same as FX
}

# Price drift tolerance: max % deviation from entry price
PRICE_DRIFT_TOLERANCE = {
    "crypto": 0.005,   # 0.5% for crypto
    "fx": 0.002,       # 0.2% for forex
    "stock": 0.003,    # 0.3% for stocks
    "commodity": 0.004 # 0.4% for commodities
}

# Candle staleness multiplier: max age = timeframe * this value
CANDLE_STALENESS_MULTIPLIER = 2

# News sentiment threshold for conflict detection
STRONG_SENTIMENT_THRESHOLD = 2

# Active signal monitoring
ACTIVE_SIGNAL_LOOKBACK_HOURS = 24
