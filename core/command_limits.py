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


def get_gemini_audit_limit(tier: str) -> int:
    """Get the daily Gemini audit limit for a given tier."""
    t = str(tier or "free").strip().lower()
    return GEMINI_AUDIT_DAILY_LIMIT.get(t, GEMINI_AUDIT_DAILY_LIMIT["free"])


def get_gemini_audit_remaining(user_id: int, tier: str, redis_client=None) -> int:
    """Get remaining Gemini audits for today for a user. Returns -1 if unlimited."""
    limit = get_gemini_audit_limit(tier)
    if limit >= 999:
        return 999  # Unlimited

    # Calculate remaining based on Redis counter
    try:
        from datetime import datetime
        from core.redis_state import state

        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        key = f"gemini_audit:{user_id}:{date_str}"

        if redis_client:
            used = int(redis_client.get(key) or 0)
        else:
            used = int(state.get_sync(key) or 0)

        remaining = max(0, limit - used)
        return remaining
    except Exception:
        return limit  # Default to full limit on error


def check_gemini_audit_rate_limit(user_id: int, tier: str) -> tuple[bool, str]:
    """Check if user can perform a Gemini audit. Returns (allowed, reason_if_not)."""
    from signalrank_telegram.access import resolve_user_tier

    # Resolve tier if not provided
    if not tier:
        try:
            tier = str(resolve_user_tier(int(user_id)) or "free")
        except Exception:
            tier = "free"

    # Owner/admin always allowed
    if tier.upper() in ("OWNER", "ADMIN"):
        return True, ""

    limit = get_gemini_audit_limit(tier)
    if limit >= 999:
        return True, ""

    # Check Redis counter
    remaining = get_gemini_audit_remaining(user_id, tier)
    if remaining <= 0:
        tier_display = tier.upper()
        return False, f"Daily {tier_display} limit reached. Upgrade to Premium for unlimited Gemini audits."

    return True, ""


def increment_gemini_audit_counter(user_id: int, redis_client=None) -> None:
    """Increment the Gemini audit counter for today."""
    try:
        from datetime import datetime

        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        key = f"gemini_audit:{user_id}:{date_str}"

        if redis_client:
            redis_client.incr(key)
            redis_client.expire(key, 86400 * 2)  # Expire after 2 days
        else:
            from core.redis_state import state
            state.set_sync(key, "1", ex=86400 * 2)
    except Exception:
        pass  # Best effort
