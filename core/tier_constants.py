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
