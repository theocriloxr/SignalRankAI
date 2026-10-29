"""Per-account limit on failed password sign-ins (29 Oct 2026 threat model).

The route rate limit keys on the first ``X-Forwarded-For`` address, which the
client controls, so rotating that header bypassed it. This limit keys on the
canonical email instead. Failures count for any email, registered or not, so
the lock reveals nothing about which accounts exist. A locked account can still
sign in with an email link or reset its password. A success does not reset
the count: the store's writes are queued, so a reset could race the next
failures; ten failures inside the window is the whole rule.
"""
from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default)) or default))
    except ValueError:
        return default


def max_failures() -> int:
    return _env_int("LOGIN_MAX_FAILURES_PER_ACCOUNT", 10, 3)


def window_seconds() -> int:
    return _env_int("LOGIN_FAILURE_WINDOW_SECONDS", 900, 60)


def _key(email: str) -> str:
    from services.platform.identity import canonical_email

    try:
        value = canonical_email(email)
    except Exception:
        value = str(email or "").strip().lower()
    return "login_failures:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]


def _lock_key(email: str) -> str:
    return _key(email) + ":locked"


def is_locked(email: str) -> bool:
    """True while the account's lock flag is set.

    The counter itself is never read back: ``get_sync`` caches values for 30
    seconds per process, which would hide later increments. A lock flag that
    has never been set is not cached, so every process sees it once set.
    """
    from core.redis_state import state

    try:
        return str(state.get_sync(_lock_key(email)) or "") == "1"
    except Exception as exc:
        # Availability over lockout, like the route limiter; the outage is logged.
        logger.warning("[login_throttle] store unavailable err=%s", type(exc).__name__)
        return False


def record_failure(email: str) -> int:
    from core.redis_state import state

    try:
        count = int(state.incr_sync(_key(email), ex=window_seconds()) or 0)
        if count >= max_failures():
            state.set_sync(_lock_key(email), "1", ex=window_seconds())
    except Exception as exc:
        logger.warning("[login_throttle] could not record failure err=%s", type(exc).__name__)
        return 0
    if count == max_failures():
        logger.warning("[login_throttle] account sign-in locked for %ss after %s failures", window_seconds(), count)
    return count


__all__ = ["is_locked", "max_failures", "record_failure", "window_seconds"]
