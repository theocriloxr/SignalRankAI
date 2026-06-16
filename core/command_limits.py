"""Canonical limits for command throttling and free-tier signal exposure."""

from __future__ import annotations

from typing import Final

from core.tier_constants import TIER_DAILY_LIMITS, TIER_SCORE_THRESHOLDS


# Command throttling profiles
REQUIRE_TIER_RATE_LIMIT: Final[dict[str, int]] = {"limit": 20, "window_seconds": 60}
PUBLIC_COMMAND_RATE_LIMIT: Final[dict[str, int]] = {"limit": 30, "window_seconds": 60}
START_COMMAND_RATE_LIMIT: Final[dict[str, int]] = {"limit": 10, "window_seconds": 30}


# Gemini Audit Rate Limits
# - Standard (FREE) users: 3 Gemini Audits per day
# - Premium users: Unlimited Gemini Audits
GEMINI_AUDIT_DAILY_LIMIT: Final[dict[str, int]] = {
    "free": 3,
    "premium": 999,  # Unlimited (practically)
    "vip": 999,
    "owner": 999,
    "admin": 999,
}


# Free-tier feed exposure constants
FREE_MIN_SCORE: Final[float] = float(TIER_SCORE_THRESHOLDS.get("free", 80) or 80)
FREE_SIGNAL_DAILY_LIMIT: Final[int] = int(TIER_DAILY_LIMITS.get("free", 3) or 3)
