"""Canonical limits for command throttling and free-tier signal exposure."""

from __future__ import annotations

from typing import Final

from core.tier_constants import TIER_DAILY_LIMITS, TIER_SCORE_THRESHOLDS


# Command throttling profiles
REQUIRE_TIER_RATE_LIMIT: Final[dict[str, int]] = {"limit": 20, "window_seconds": 60}
PUBLIC_COMMAND_RATE_LIMIT: Final[dict[str, int]] = {"limit": 30, "window_seconds": 60}
START_COMMAND_RATE_LIMIT: Final[dict[str, int]] = {"limit": 10, "window_seconds": 30}

# Gemini Audit Rate Limits
# - Standard/free users: 3 Gemini Audits per day
# - Paid/staff tiers: effectively unlimited
GEMINI_AUDIT_DAILY_LIMIT: Final[dict[str, int]] = {
    "free": 3,
    "premium": 999,
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
    """Get remaining Gemini audits for today for a user."""
    limit = get_gemini_audit_limit(tier)
    if limit >= 999:
        return 999

    try:
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"gemini_audit:{user_id}:{date_str}"
        if redis_client:
            used = int(redis_client.get(key) or 0)
        else:
            from core.redis_state import state

            used = int(state.get_sync(key) or 0)
        return max(0, limit - used)
    except Exception:
        return limit


def check_gemini_audit_rate_limit(user_id: int, tier: str) -> tuple[bool, str]:
    """Check if user can perform a Gemini audit."""
    if not tier:
        try:
            from signalrank_telegram.access import resolve_user_tier

            tier = str(resolve_user_tier(int(user_id)) or "free")
        except Exception:
            tier = "free"

    if str(tier or "").upper() in {"OWNER", "ADMIN"}:
        return True, ""

    limit = get_gemini_audit_limit(tier)
    if limit >= 999:
        return True, ""

    remaining = get_gemini_audit_remaining(user_id, tier)
    if remaining <= 0:
        return False, f"Daily {str(tier).upper()} limit reached. Upgrade to Premium for unlimited Gemini audits."
    return True, ""


def increment_gemini_audit_counter(user_id: int, redis_client=None) -> None:
    """Increment the Gemini audit counter for today."""
    try:
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"gemini_audit:{user_id}:{date_str}"
        if redis_client:
            redis_client.incr(key)
            redis_client.expire(key, 86400 * 2)
        else:
            from core.redis_state import state

            current = int(state.get_sync(key) or 0)
            state.set_sync(key, str(current + 1), ex=86400 * 2)
    except Exception:
        pass
