"""
SignalRankAI — Tier Constants (PERFECTED)

Single source of truth for all tier-based limits, thresholds, and feature flags.
All modules MUST import from here rather than defining their own tier logic.

Tier hierarchy:
  FREE < PREMIUM < VIP = ADMIN = OWNER

Subscription tiers:
  free     → 3 signals/day, limited format, no exact levels
  premium  → 10 signals/day, full format, no TP3, no AI
  vip      → 30 signals/day, VIP format, all levels, Gemini AI, MT5 auto
  admin    → Same as VIP (staff access)
  owner    → Same as VIP (platform owner)
"""

from __future__ import annotations

import os
from typing import Dict


# ─── Daily signal limits per tier ─────────────────────────────────────────────

TIER_DAILY_LIMITS: Dict[str, int] = {
    "free":    int(os.getenv("FREE_DAILY_LIMIT",    "3")   or 3),
    "premium": int(os.getenv("PREMIUM_DAILY_LIMIT", "10")  or 10),
    "vip":     int(os.getenv("VIP_DAILY_LIMIT",     "30")  or 30),
    "admin":   int(os.getenv("VIP_DAILY_LIMIT",     "30")  or 30),  # Same as VIP
    "owner":   int(os.getenv("VIP_DAILY_LIMIT",     "30")  or 30),  # Same as VIP
}


# ─── Minimum score thresholds for signal delivery ─────────────────────────────

TIER_MIN_SCORES: Dict[str, float] = {
    "free":    float(os.getenv("FREE_MIN_SCORE",    "55") or 55),   # Any decent signal
    "premium": float(os.getenv("PREMIUM_MIN_SCORE", "60") or 60),   # Above average
    "vip":     float(os.getenv("VIP_MIN_SCORE",     "72") or 72),   # High conviction only
    "admin":   float(os.getenv("VIP_MIN_SCORE",     "72") or 72),
    "owner":   float(os.getenv("VIP_MIN_SCORE",     "72") or 72),
}


# ─── Tier feature flags ────────────────────────────────────────────────────────

TIER_FEATURES: Dict[str, Dict[str, bool]] = {
    "free": {
        "exact_entry":      False,
        "exact_sl":         False,
        "exact_tp1":        False,   # Shows "near zone" only
        "tp2":              False,
        "tp3":              False,
        "r_multiple":       False,
        "regime":           False,
        "gemini_ai":        False,
        "mt5_execute":      False,
        "webhook_api":      False,
        "live_monitoring":  False,
        "performance_stats":False,
        "signal_chart":     False,
        "outcome_detail":   False,   # Only sees win/loss, no %
        "signal_history":   False,
        "priority_delivery":False,
    },
    "premium": {
        "exact_entry":      True,
        "exact_sl":         True,
        "exact_tp1":        True,
        "tp2":              True,
        "tp3":              False,   # No TP3 for premium
        "r_multiple":       True,
        "regime":           False,
        "gemini_ai":        False,
        "mt5_execute":      True,    # Manual execution only
        "webhook_api":      False,
        "live_monitoring":  True,
        "performance_stats":True,
        "signal_chart":     True,
        "outcome_detail":   True,
        "signal_history":   True,
        "priority_delivery":False,
    },
    "vip": {
        "exact_entry":      True,
        "exact_sl":         True,
        "exact_tp1":        True,
        "tp2":              True,
        "tp3":              True,    # Full TP3 for VIP
        "r_multiple":       True,
        "regime":           True,    # Market regime context
        "gemini_ai":        True,    # 🤖 Ask Gemini Why
        "mt5_execute":      True,    # Manual + AUTO execution
        "webhook_api":      True,    # Webhook for Cornix/PineConnector
        "live_monitoring":  True,
        "performance_stats":True,
        "signal_chart":     True,
        "outcome_detail":   True,
        "signal_history":   True,
        "priority_delivery":True,    # Gets signals before premium/free
    },
}

# Admin and owner have same features as VIP
TIER_FEATURES["admin"] = TIER_FEATURES["vip"]
TIER_FEATURES["owner"] = TIER_FEATURES["vip"]


# ─── Tier rank for comparison ──────────────────────────────────────────────────

TIER_RANK: Dict[str, int] = {
    "free":    0,
    "premium": 1,
    "vip":     2,
    "admin":   2,
    "owner":   2,
}


def tier_rank(tier: str) -> int:
    """Return numeric rank for tier comparison (higher = more access)."""
    return TIER_RANK.get(str(tier or "free").lower(), 0)


def normalize_tier(tier: str | None) -> str:
    """Normalize a tier string to canonical lowercase form."""
    t = str(tier or "free").strip().lower()
    if t in ("owner", "admin"):
        return "vip"  # Owner/admin get VIP features
    if t not in TIER_RANK:
        return "free"
    return t


def has_feature(tier: str, feature: str) -> bool:
    """Check if a tier has a specific feature enabled."""
    t = str(tier or "free").strip().lower()
    return bool(TIER_FEATURES.get(t, TIER_FEATURES["free"]).get(feature, False))


def get_daily_limit(tier: str) -> int:
    """Return the daily signal limit for a tier."""
    t = str(tier or "free").strip().lower()
    return int(TIER_DAILY_LIMITS.get(t, TIER_DAILY_LIMITS["free"]))


def get_min_score(tier: str) -> float:
    """Return the minimum signal score threshold for a tier."""
    t = str(tier or "free").strip().lower()
    return float(TIER_MIN_SCORES.get(t, TIER_MIN_SCORES["free"]))


# ─── Pricing ──────────────────────────────────────────────────────────────────

TIER_PRICES_NGN: Dict[str, int] = {
    "premium": int(os.getenv("PREMIUM_PRICE_NGN", "5000")  or 5000),
    "vip":     int(os.getenv("VIP_PRICE_NGN",     "15000") or 15000),
}

TIER_PRICES_USD: Dict[str, float] = {
    "premium": float(os.getenv("PREMIUM_PRICE_USD", "10.0") or 10.0),
    "vip":     float(os.getenv("VIP_PRICE_USD",     "30.0") or 30.0),
}

TIER_BILLING_PERIODS: Dict[str, str] = {
    "premium": "monthly",
    "vip":     "monthly",
}


# ─── Tier display names ────────────────────────────────────────────────────────

TIER_DISPLAY_NAMES: Dict[str, str] = {
    "free":    "Free",
    "premium": "Premium ⭐",
    "vip":     "VIP 👑",
    "admin":   "Admin 🛡️",
    "owner":   "Owner 🔑",
}

TIER_EMOJIS: Dict[str, str] = {
    "free":    "🆓",
    "premium": "⭐",
    "vip":     "👑",
    "admin":   "🛡️",
    "owner":   "🔑",
}


# ─── Asset repeat cooldown (prevents sending same asset twice) ─────────────────

TIER_ASSET_COOLDOWN_HOURS: Dict[str, int] = {
    "free":    int(os.getenv("FREE_ASSET_COOLDOWN_HOURS",    "12") or 12),
    "premium": int(os.getenv("PREMIUM_ASSET_COOLDOWN_HOURS", "8")  or 8),
    "vip":     int(os.getenv("VIP_ASSET_COOLDOWN_HOURS",     "4")  or 4),
    "admin":   int(os.getenv("VIP_ASSET_COOLDOWN_HOURS",     "4")  or 4),
    "owner":   int(os.getenv("VIP_ASSET_COOLDOWN_HOURS",     "4")  or 4),
}


# ─── Engine / strategy compatibility constants ────────────────────────────────
# Backward-compatible export used by strategies.dynamic_targets and related
# expectancy/risk gates. This value is intentionally env-configurable.
EXPECTANCY_MIN: float = float(os.getenv("EXPECTANCY_MIN", "0.0") or 0.0)


# ─── Candle freshness / staleness constants ───────────────────────────────────
# Used by engine core data-age gate: max_age = tf_seconds * CANDLE_STALENESS_MULTIPLIER
CANDLE_STALENESS_MULTIPLIER: float = float(
    os.getenv("CANDLE_STALENESS_MULTIPLIER", "2.0") or 2.0
)


# ─── News / sentiment gating constants ────────────────────────────────────────
# Strong opposing sentiment threshold used by engine news confirmation gate.
STRONG_SENTIMENT_THRESHOLD: float = float(
    os.getenv("STRONG_SENTIMENT_THRESHOLD", "2.0") or 2.0
)


# ─── VIP capacity cap ─────────────────────────────────────────────────────────

VIP_MAX_CAPACITY: int = int(os.getenv("VIP_MAX_CAPACITY", "30") or 30)


__all__ = [
    "TIER_DAILY_LIMITS",
    "TIER_MIN_SCORES",
    "TIER_FEATURES",
    "TIER_RANK",
    "TIER_PRICES_NGN",
    "TIER_PRICES_USD",
    "TIER_BILLING_PERIODS",
    "TIER_DISPLAY_NAMES",
    "TIER_EMOJIS",
    "TIER_ASSET_COOLDOWN_HOURS",
    "EXPECTANCY_MIN",
    "CANDLE_STALENESS_MULTIPLIER",
    "STRONG_SENTIMENT_THRESHOLD",
    "VIP_MAX_CAPACITY",
    "tier_rank",
    "normalize_tier",
    "has_feature",
    "get_daily_limit",
    "get_min_score",
]