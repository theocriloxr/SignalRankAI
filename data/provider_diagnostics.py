"""Why a market-data connector returned no candles.

Connectors return ``[]`` for every failure: a missing API key, an active
rate-limit cooldown, an HTTP error or an empty provider response. Production
logged all of them as ``insufficient_candles candles=0`` (28 Oct 2026: every FX,
index and commodity request failed that way), so the cause could not be read
from the logs. Connectors now note the cause here; the fetcher appends it to
the failure reason it already logs, and each provider/cause pair is warned at
most once per ``PROVIDER_DIAGNOSTIC_WARN_SECONDS``. Secrets are never recorded.
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger("data.provider_diagnostics")

_lock = threading.Lock()
_last: dict[str, tuple[str, float]] = {}
_warned: dict[tuple[str, str], float] = {}


def _key(provider: str) -> str:
    return str(provider or "").strip().lower().removesuffix("_connector")


def note(provider: str, cause: str) -> None:
    """Record the cause of an empty result; warn once per provider/cause window."""
    key, cause = _key(provider), str(cause or "unknown")[:64]
    now = time.monotonic()
    try:
        window = max(60.0, float(os.getenv("PROVIDER_DIAGNOSTIC_WARN_SECONDS", "900") or 900))
    except ValueError:
        window = 900.0
    with _lock:
        _last[key] = (cause, now)
        last_warned = _warned.get((key, cause))
        should_warn = last_warned is None or now - last_warned >= window
        if should_warn:
            _warned[(key, cause)] = now
    if should_warn:
        logger.warning("[provider_unavailable] provider=%s cause=%s", key, cause)


def recent(provider: str, max_age_seconds: float = 30.0) -> str | None:
    """The cause noted for ``provider`` within ``max_age_seconds``, if any."""
    with _lock:
        entry = _last.get(_key(provider))
    if entry is None or time.monotonic() - entry[1] > max_age_seconds:
        return None
    return entry[0]


def reset() -> None:
    with _lock:
        _last.clear()
        _warned.clear()


__all__ = ["note", "recent", "reset"]
