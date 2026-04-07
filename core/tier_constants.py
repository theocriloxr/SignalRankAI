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
    "premium": 75,
    "vip": 75,
    "owner": 75,
    "admin": 75,
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

# Price drift tolerance: max fractional deviation from entry price (not %).
# These mirror the % values in engine/stale_signal_validator._CLASS_THRESHOLDS.
PRICE_DRIFT_TOLERANCE = {
    "crypto":    0.020,  # 2.0 % — volatile 24/7 market; full cycle can take 30-120 s
    "fx":        0.003,  # 0.3 % — tight spreads; FX moves slowly relative to crypto
    "stock":     0.010,  # 1.0 % — intraday moves justify 1 % tolerance
    "commodity": 0.008,  # 0.8 % — between FX and stock volatility
}

# Candle staleness multiplier: max age = timeframe * this value
CANDLE_STALENESS_MULTIPLIER = 2

# News sentiment threshold for conflict detection
STRONG_SENTIMENT_THRESHOLD = 2

# Active signal monitoring
ACTIVE_SIGNAL_LOOKBACK_HOURS = 24
