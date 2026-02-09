"""Shared tier constants and limits for signal delivery."""

# Tier daily signal limits
TIER_DAILY_LIMITS = {
    "free": 2,
    "premium": 20,
    "vip": float('inf'),
    "owner": float('inf'),
    "admin": float('inf'),
}

# Tier quality score thresholds
TIER_SCORE_THRESHOLDS = {
    "free": 70,
    "premium": 55,
    "vip": 45,
    "owner": 45,
    "admin": 45,
}

# Signal freshness: max age in seconds before signal is considered stale
MAX_SIGNAL_AGE_SECONDS = {
    "crypto": 180,   # 3 minutes for crypto (fast-moving markets)
    "fx": 300,       # 5 minutes for forex
    "stock": 300,    # 5 minutes for stocks
    "commodity": 300 # 5 minutes for commodities
}

# Price drift tolerance: max % deviation from entry price
PRICE_DRIFT_TOLERANCE = {
    "crypto": 0.005,   # 0.5% for crypto
    "fx": 0.002,       # 0.2% for forex
    "stock": 0.003,    # 0.3% for stocks
    "commodity": 0.004 # 0.4% for commodities
}
