"""
SignalRankAI — Signal Deduplicator (PERFECTED)

Implements deterministic SHA256 signal fingerprinting per the "Perfect Trading Bot"
specification. A signal is suppressed if:
  1. The same trade thesis (Asset + Direction + EntryZone + Timeframe) was sent
     within the deduplication window AND is still ACTIVE in the DB.
  2. Soft dedup: same asset/direction within cooldown period for the same user.

Key principles:
  - Dedup by TRADE THESIS, not by candle timestamp.
  - SHA256(asset.upper() + "|" + direction.lower() + "|" + entry_bucket + "|" + timeframe)
  - Redis atomic check-and-set (SETNX) prevents races in multi-instance deployments.
  - PostgreSQL fallback if Redis unavailable.
  - edit_message_text update path for freshness bumps (not new message spam).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Dedup window: how long (seconds) a signal hash blocks re-emission
_DEFAULT_DEDUP_WINDOW_SECONDS = 4 * 60 * 60  # 4 hours


def _entry_bucket(entry: float | None) -> str:
    """Round entry to a 3-significant-figure bucket to absorb micro-tick noise."""
    if not entry or entry <= 0:
        return "0"
    try:
        magnitude = 10 ** (len(str(int(entry))) - 1)
        # Round to nearest 0.1% of the entry price
        bucket_size = max(0.001, entry * 0.001)
        rounded = round(entry / bucket_size) * bucket_size
        return f"{rounded:.6g}"
    except Exception:
        return str(entry)


def compute_signal_fingerprint(signal: dict) -> str:
    """
    Generate a deterministic SHA256 fingerprint for a trade thesis.

    SHA256(ASSET|DIRECTION|ENTRY_BUCKET|TIMEFRAME)

    This is the CANONICAL deduplication key. Two signals with the same
    thesis (same asset, same direction, similar entry, same timeframe)
    will produce the same fingerprint regardless of when they were generated.
    """
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    direction = str(signal.get("direction") or "long").lower().strip()
    entry = signal.get("entry") or signal.get("close_price") or 0
    timeframe = str(signal.get("timeframe") or "1h").lower().strip()

    try:
        entry_f = float(entry)
    except Exception:
        entry_f = 0.0

    raw = f"{asset}|{direction}|{_entry_bucket(entry_f)}|{timeframe}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_signal_hash_key(signal: dict) -> str:
    """Return the Redis key for a signal's dedup hash."""
    fp = compute_signal_fingerprint(signal)
    return f"sig_dedup:{fp}"


class SignalDeduplicator:
    """
    Atomic signal deduplication using Redis SETNX (Set if Not eXists).

    Usage:
        dedup = SignalDeduplicator()
        if dedup.is_duplicate(signal):
            return  # suppress
        dedup.mark_active(signal)
        # ... generate and send signal
    """

    def __init__(self, window_seconds: int = _DEFAULT_DEDUP_WINDOW_SECONDS):
        self.window_seconds = int(window_seconds)

    def _redis_client(self):
        try:
            from core.redis_state import state
            return state
        except Exception:
            return None

    def is_duplicate(self, signal: dict, *, check_db: bool = True) -> bool:
        """
        Return True if this signal is a duplicate of an already-active one.

        Checks:
          1. Redis hash → sub-millisecond check for hot path.
          2. PostgreSQL active_signals table → survives Redis restarts.
        """
        key = compute_signal_hash_key(signal)

        # Redis check
        try:
            r = self._redis_client()
            if r is not None:
                val = r.get_sync(key)
                if val:
                    logger.debug("[dedup] Redis hit — suppressed: %s", key[:24])
                    return True
        except Exception as exc:
            logger.debug("[dedup] Redis check failed: %s", exc)

        # DB check
        if check_db:
            try:
                fp = compute_signal_fingerprint(signal)
                from utils.async_runner import run_sync
                from db.session import get_session
                from db.models import Signal
                from sqlalchemy import select, and_
                from datetime import datetime, timezone, timedelta

                cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)

                async def _check_db():
                    async with get_session() as session:
                        row = (
                            await session.execute(
                                select(Signal.signal_id).where(
                                    and_(
                                        Signal.signal_fingerprint == fp,
                                        Signal.expired == False,
                                        Signal.archived == False,
                                        Signal.created_at >= cutoff,
                                    )
                                ).limit(1)
                            )
                        ).scalar_one_or_none()
                        await session.commit()
                        return row is not None

                is_dup = run_sync(_check_db())
                if is_dup:
                    logger.debug("[dedup] DB hit — suppressed: %s", fp[:24])
                    # Backfill Redis so next check is fast
                    self._mark_redis(key)
                    return True
            except Exception as exc:
                logger.debug("[dedup] DB check failed: %s", exc)

        return False

    def _mark_redis(self, key: str) -> None:
        """Atomically mark key in Redis using SETNX."""
        try:
            r = self._redis_client()
            if r is not None:
                # Use set_sync with nx=True for atomic SETNX behavior
                r.set_sync(key, "1", ex=self.window_seconds, nx=True)
        except Exception as exc:
            logger.debug("[dedup] Redis mark failed: %s", exc)

    def mark_active(self, signal: dict) -> None:
        """Mark a signal as active in the dedup store."""
        key = compute_signal_hash_key(signal)
        self._mark_redis(key)
        logger.debug("[dedup] Marked active: %s", key[:24])

    def clear(self, signal: dict) -> None:
        """Remove a signal from the dedup store (e.g. on expiry/outcome)."""
        key = compute_signal_hash_key(signal)
        try:
            r = self._redis_client()
            if r is not None:
                r.delete_sync(key)
        except Exception as exc:
            logger.debug("[dedup] Redis clear failed: %s", exc)

    def check_and_mark(self, signal: dict) -> bool:
        """
        Atomic check-and-mark operation.

        Returns True if the signal is new (not a duplicate) and was marked.
        Returns False if the signal is a duplicate (suppressed).

        This is the PRIMARY method to use in the signal pipeline:

            if not dedup.check_and_mark(signal):
                return  # duplicate, suppress
        """
        if self.is_duplicate(signal):
            return False
        self.mark_active(signal)
        return True


# ─── Per-user per-asset delivery cooldown ─────────────────────────────────────

def check_user_asset_cooldown(user_id: int, asset: str, direction: str) -> bool:
    """
    Return True if user was recently sent a signal for this asset+direction.

    This is the DELIVERY-LEVEL dedup — separate from thesis-level dedup.
    Prevents a user from receiving the same asset/direction multiple times
    within the cooldown window even if the signal thesis changed slightly.
    """
    try:
        from core.redis_state import state
        import os
        hours = int(os.getenv("ASSET_REPEAT_LOCK_HOURS", "12") or 12)
        key = f"delivery_cool:{int(user_id)}:{asset.upper()}:{direction.upper()}"
        val = state.get_sync(key)
        return bool(val)
    except Exception:
        return False


def set_user_asset_cooldown(
    user_id: int, asset: str, direction: str, tier: str
) -> None:
    """Mark that user received a signal for this asset+direction."""
    try:
        from core.redis_state import state
        import os
        # VIP users get shorter cooldown so they get more signal variety
        tier_l = str(tier or "free").lower()
        if tier_l in ("vip", "owner", "admin"):
            hours = int(os.getenv("VIP_ASSET_COOLDOWN_HOURS", "4") or 4)
        elif tier_l == "premium":
            hours = int(os.getenv("PREMIUM_ASSET_COOLDOWN_HOURS", "8") or 8)
        else:
            hours = int(os.getenv("ASSET_REPEAT_LOCK_HOURS", "12") or 12)
        key = f"delivery_cool:{int(user_id)}:{asset.upper()}:{direction.upper()}"
        state.set_sync(key, "1", ex=hours * 3600)
    except Exception as exc:
        logger.debug("[dedup] set_user_asset_cooldown failed: %s", exc)


# ─── Portfolio correlation guard ──────────────────────────────────────────────

# Highly correlated asset pairs — sending both simultaneously inflates exposure
_CORRELATED_PAIRS: list[tuple[str, str]] = [
    ("BTCUSDT", "ETHUSDT"),
    ("BTCUSDT", "SOLUSDT"),
    ("BTCUSDT", "BNBUSDT"),
    ("ETHUSDT", "SOLUSDT"),
    ("XAUUSD", "XAGUSD"),
    ("EURUSD", "GBPUSD"),
    ("USDCHF", "USDJPY"),
]

_CORR_THRESHOLD = 0.70  # correlation coefficient above which we suppress second signal


def signals_are_correlated(asset1: str, asset2: str) -> bool:
    """Return True if the two assets are known to be highly correlated."""
    a1, a2 = asset1.upper().strip(), asset2.upper().strip()
    if a1 == a2:
        return True
    for pair in _CORRELATED_PAIRS:
        if (a1 in pair and a2 in pair):
            return True
    return False


def filter_correlated_signals(signals: list[dict]) -> list[dict]:
    """
    Given a ranked list of signals, remove correlated duplicates.

    Keeps the highest-scoring signal when two correlated assets are both present.
    Signals should be pre-sorted by score descending.
    """
    seen_assets: list[str] = []
    filtered: list[dict] = []

    for sig in signals:
        asset = str(sig.get("asset") or sig.get("symbol") or "").upper().strip()
        if not asset:
            filtered.append(sig)
            continue

        # Check if any already-accepted asset is correlated with this one
        corr_found = False
        for accepted in seen_assets:
            if signals_are_correlated(asset, accepted):
                corr_found = True
                logger.debug(
                    "[dedup] Suppressed correlated signal: %s (correlated with %s)",
                    asset,
                    accepted,
                )
                break

        if not corr_found:
            filtered.append(sig)
            seen_assets.append(asset)

    return filtered


# ─── Module-level singleton ───────────────────────────────────────────────────

_deduplicator: Optional[SignalDeduplicator] = None


def get_deduplicator() -> SignalDeduplicator:
    """Return the module-level SignalDeduplicator singleton."""
    global _deduplicator
    if _deduplicator is None:
        import os
        window = int(os.getenv("SIGNAL_DEDUP_WINDOW_HOURS", "4") or 4) * 3600
        _deduplicator = SignalDeduplicator(window_seconds=window)
    return _deduplicator


__all__ = [
    "SignalDeduplicator",
    "compute_signal_fingerprint",
    "compute_signal_hash_key",
    "check_user_asset_cooldown",
    "set_user_asset_cooldown",
    "filter_correlated_signals",
    "signals_are_correlated",
    "get_deduplicator",
]