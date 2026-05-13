"""Shared tier constants and limits for signal delivery.

CANONICAL TIER & DELIVERY MODEL (2026-04-12):

Tier Quality Tiers (Score-based):
  - FREE: 80+ (most restrictive quality gate, limited detail in messages)
  - PREMIUM: 70+ (more opportunity, medium detail)
  - VIP: 75+ (quality filter with deeper TP ladder)
  - ADMIN: 0+ (all signals for monitoring)
  - OWNER: 0+ (unlimited, receives everything)

Daily Limits (PER DELIVERED SIGNALS to user):
  - FREE: 3 signals/day (hard cap)
  - PREMIUM: 10 signals/day (hard cap, resets at user's local midnight)
  - VIP: 20 signals/day (quality-based soft cap, pauses after 20)
  - OWNER: unlimited

Signal Depth (TP Levels Shown):
  - FREE: TP1, TP2, SL (TP2 is their 'max')
  - PREMIUM: TP1, TP2, SL (same depth as FREE)
  - VIP: TP1, TP2, TP3, SL (full ladder, TP3 is their 'max')
  - OWNER: All TP levels + all outcomes

Delivery Model:
  - Engine generates signals in cycles
  - Signals are RANDOMLY SAMPLED to eligible users per tier
  - Random sampling is PURE (users can permanently miss some signals)
  - Daily limits enforce DELIVERED signals (not eligible signals)
  - Upgrade backfill: only signals already sampled to user (no re-delivery of missed ones)
  - Outcome tracking is strict per (user, signal) pair

Outcome Rules:
  - Once TP is hit on a signal, no SL outcome can be recorded
  - TP progression shows as \"1/3\", \"2/3\", \"3/3\"
  - SL outcome only recorded if no TP was hit
  - Trailing SL: track outcomes against CURRENT SL, not original SL

NEW PRODUCTION UPGRADES (2024):
  - EXPECTANCY_MIN=0.15 (live block below this)
  - DD_SOFT_THROTTLE=0.06, DD_HARD=0.12
  - CANDLE_STALENESS_MULTIPLIER=1.5 (stricter freshness)
"""

from typing import Final

# Tier daily signal limits (DELIVERED signals per user)
TIER_DAILY_LIMITS: Final[dict[str, float]] = {
    "free": 3.0,
    "premium": 10.0,
    "vip": 20.0,  # Soft cap, signals pause after 20/day
    "owner": float('inf'),
    "admin": float('inf'),
}

# Tier quality score thresholds (minimum signal score to be eligible)
TIER_SCORE_THRESHOLDS: Final[dict[str, float]] = {
    "free": 80.0,      # Highest quality only
    "premium": 70.0,   # Lower threshold = more signals
    "vip": 75.0,       # Quality filter with deeper TP ladder
    "owner": 0.0,      # No score gate
    "admin": 0.0,      # Admin receives all signals
}

# Signal depth per tier (how many TP levels shown)
TIER_SIGNAL_DEPTH: Final[dict[str, dict]] = {
    "free": {
        "max_tp_level": 2,  # Shows TP1, TP2
        "show_tp3": False,
        "show_sl": True,
        "detail_level": "basic",  # Limited details, with upgrade prompt
    },
    "premium": {
        "max_tp_level": 2,  # Shows TP1, TP2
        "show_tp3": False,
        "show_sl": True,
        "detail_level": "full",
    },
    "vip": {
        "max_tp_level": 3,  # Shows TP1, TP2, TP3
        "show_tp3": True,
        "show_sl": True,
        "detail_level": "full",
    },
    "owner": {
        "max_tp_level": 3,
        "show_tp3": True,
        "show_sl": True,
        "detail_level": "full",
    },
    "admin": {
        "max_tp_level": 3,
        "show_tp3": True,
        "show_sl": True,
        "detail_level": "full",
    },
}

# Tier upgrade prompt frequency (for FREE users)
UPGRADE_PROMPT_FREQUENCY: Final[str] = "smart"  # Show on strategic signals to maximize conversion
UPGRADE_PROMPT_FREQUENCY_INT: Final[int] = 3  # Every 3rd signal, or based on signal quality

# Signal freshness: max age in seconds before signal is considered stale.
# Keep this strict and centralized as the single source for freshness policy.
MAX_SIGNAL_AGE_SECONDS: Final[dict[str, int]] = {
    "crypto":    300,    # 5 min
    "fx":        900,    # 15 min
    "stock":     900,    # 15 min
    "commodity": 900,    # 15 min
}

# Price drift tolerance: max fractional deviation from entry price (not %).
# These mirror the % values in engine/stale_signal_validator._CLASS_THRESHOLDS.
PRICE_DRIFT_TOLERANCE: Final[dict[str, float]] = {
    "crypto":    0.020,  # 2.0 % — volatile 24/7 market; full cycle can take 30-120 s
    "fx":        0.003,  # 0.3 % — tight spreads; FX moves slowly relative to crypto
    "stock":     0.010,  # 1.0 % — intraday moves justify 1 % tolerance
    "commodity": 0.008,  # 0.8 % — between FX and stock volatility
}

# Candle staleness multiplier: max age = timeframe * this value
# For Railway Hobby tier, use 24x to allow signals even if data is hours behind
import os as _os
_is_railway = bool((_os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (_os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
CANDLE_STALENESS_MULTIPLIER: Final[float] = float(_os.getenv("CANDLE_STALENESS_MULTIPLIER", "24.0" if _is_railway else "1.5"))

# NEW PRODUCTION RISK CONSTANTS
EXPECTANCY_MIN: Final[float] = 0.15  # Block signals from assets/strategies with expectancy < 0.15
DD_SOFT_THROTTLE: Final[float] = 0.06  # Throttle signals at 6% drawdown
DD_HARD_LIMIT: Final[float] = 0.12  # Hard stop at 12% drawdown

# News sentiment threshold for conflict detection
STRONG_SENTIMENT_THRESHOLD: Final[int] = 2

# Active signal monitoring
ACTIVE_SIGNAL_LOOKBACK_HOURS: Final[int] = 24

# FREE tier specific constants
FREE_MIN_SCORE: Final[int] = 80  # Minimum signal score for FREE tier eligibility
FREE_SIGNAL_DAILY_LIMIT: Final[int] = 3  # Daily signal limit for FREE users
FREE_PROOF_FEED_LIMIT: Final[int] = 5  # Max signals shown in FREE proof feed

