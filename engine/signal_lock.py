"""Redis signal-generation leases shared by synchronous and async callers.

Redis loss denies acquisition. A task/thread can release only its own token;
expiry and replacement cannot cause an old caller to delete a newer lease.
These leases accelerate deduplication; durable database uniqueness remains
necessary across Redis failover, restarts and work exceeding a lease's TTL.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)
LOCK_TTL_SECONDS = {"4h": 14400, "1d": 21600, "1h": 7200, "15m": 3600, "5m": 1800, "30m": 2700}


@dataclass(frozen=True)
class _OwnedLease:
    token: str
    owner: object
    expires_at: float


_owned: ContextVar[dict[str, _OwnedLease] | None] = ContextVar("signal_generation_leases", default=None)


def _owner() -> object:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return (threading.get_ident(), task)


def get_lock_ttl(timeframe: str) -> int:
    return LOCK_TTL_SECONDS.get(str(timeframe).lower().strip(), 14400)


def _make_lock_key(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> str:
    symbol = str(asset or "").upper().strip()
    side = str(direction or "").lower().strip()
    side = {"buy": "long", "sell": "short"}.get(side, side)
    tf = str(timeframe or "").lower().strip()
    if not re.fullmatch(r"[A-Z0-9._/=-]+", symbol) or side not in {"long", "short"} or not re.fullmatch(r"[1-9][0-9]*[mhdw]", tf):
        raise ValueError("invalid signal lock scope")
    key = f"signal_lock:{symbol}:{side}:{tf}"
    if strategy_group is not None:
        group = str(strategy_group).lower().strip()
        if not re.fullmatch(r"[a-z0-9_.-]+", group):
            raise ValueError("invalid signal lock strategy group")
        key += f":{group}"
    return key


def _legacy_keys(key: str) -> tuple[str, ...]:
    _, asset, side, tf, *group = key.split(":")
    alias = "buy" if side == "long" else "sell"
    suffix = ":" + group[0] if group else ""
    keys = [f"signal_lock:{asset}:{alias}:{tf}{suffix}", f"signal_lock:{asset}:{side.upper()}:{tf.upper()}{suffix}",
            f"signal_lock:{asset}:{alias.upper()}:{tf.upper()}{suffix}"]
    if group:
        # A historical ungrouped lock also protects the broader thesis.
        keys += [f"signal_lock:{asset}:{s}:{t}" for s, t in ((side, tf), (alias, tf), (side.upper(), tf.upper()), (alias.upper(), tf.upper()))]
    return tuple(keys)


def _remember(key: str, token: str, ttl: int) -> None:
    now = time.monotonic()
    leases = {k: v for k, v in (_owned.get() or {}).items() if v.expires_at > now}
    leases[key] = _OwnedLease(token, _owner(), now + ttl)
    _owned.set(leases)


def _take_owned(key: str) -> str | None:
    leases = _owned.get() or {}
    lease = leases.get(key)
    if lease is None or lease.owner != _owner():
        return None
    _owned.set({k: v for k, v in leases.items() if k != key})
    return lease.token


def _acquire(key: str, ttl: int) -> str | None:
    from core.redis_state import state
    return state.lease_acquire_sync(key, ttl, _legacy_keys(key))


def _blocked(key: str) -> bool:
    from core.redis_state import state
    return state.lease_blocked_sync(key, _legacy_keys(key))


def _release(key: str, token: str) -> bool:
    from core.redis_state import state
    return state.lease_release_sync(key, token)


def check_signal_lock(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
    try:
        return _blocked(_make_lock_key(asset, direction, timeframe, strategy_group))
    except Exception as exc:
        logger.warning("[signal_lock] check blocked error=%s", type(exc).__name__)
        return True


def acquire_signal_lock_sync(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None, ttl_seconds: Optional[int] = None) -> bool:
    try:
        key = _make_lock_key(asset, direction, timeframe, strategy_group)
        ttl = get_lock_ttl(timeframe) if ttl_seconds is None else ttl_seconds
        token = _acquire(key, ttl)
        if token is None:
            return False
        _remember(key, token, ttl)
        return True
    except Exception as exc:
        logger.warning("[signal_lock] acquisition denied error=%s", type(exc).__name__)
        return False


def release_signal_lock_sync(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
    try:
        key = _make_lock_key(asset, direction, timeframe, strategy_group)
        token = _take_owned(key)
        return False if token is None else _release(key, token)
    except Exception as exc:
        logger.warning("[signal_lock] release denied error=%s", type(exc).__name__)
        return False


async def is_signal_locked(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
    return await asyncio.to_thread(check_signal_lock, asset, direction, timeframe, strategy_group)


async def acquire_signal_lock(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None, ttl_seconds: Optional[int] = None) -> bool:
    try:
        key = _make_lock_key(asset, direction, timeframe, strategy_group)
        ttl = get_lock_ttl(timeframe) if ttl_seconds is None else ttl_seconds
        token = await asyncio.to_thread(_acquire, key, ttl)
        if token is None:
            return False
        # Record ownership in the calling task, not the worker thread's context.
        _remember(key, token, ttl)
        return True
    except Exception as exc:
        logger.warning("[signal_lock] acquisition denied error=%s", type(exc).__name__)
        return False


async def release_signal_lock(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
    try:
        key = _make_lock_key(asset, direction, timeframe, strategy_group)
        token = _take_owned(key)
        return False if token is None else await asyncio.to_thread(_release, key, token)
    except Exception as exc:
        logger.warning("[signal_lock] release denied error=%s", type(exc).__name__)
        return False


class SignalLock:
    async def is_allowed(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        return not await is_signal_locked(asset, direction, timeframe, strategy_group)

    async def try_acquire(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        return await acquire_signal_lock(asset, direction, timeframe, strategy_group)

    async def acquire(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        return await self.try_acquire(asset, direction, timeframe, strategy_group)

    async def release(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        return await release_signal_lock(asset, direction, timeframe, strategy_group)


signal_lock = SignalLock()


# PostgreSQL backup check function
async def active_signal_exists_for_asset(asset: str, direction: str, timeframe: str, lookback_hours: int = 24) -> bool:
    """Check if an active signal already exists for this asset/direction/timeframe.

    Uses PostgreSQL as backup when Redis is unavailable.

    Args:
        asset: Asset symbol
        direction: "long" or "short"
        timeframe: Timeframe
        lookback_hours: How far back to look for active signals

    Returns:
        True if active signal exists, False otherwise
    """
    from datetime import timedelta
    from sqlalchemy import select, and_

    try:
        from db.session import get_session
        from db.models import Signal

        cutoff = now_utc_naive() - timedelta(hours=lookback_hours)

        import os
        from sqlalchemy import or_, exists as sa_exists

        filters = [
            Signal.asset == str(asset).upper(),
            Signal.direction == str(direction).lower(),
            Signal.timeframe == str(timeframe).lower(),
            Signal.archived == False,
            Signal.expired == False,
            Signal.created_at >= cutoff,
        ]
        if str(os.getenv("ACTIVE_SIGNAL_COOLDOWN_IGNORE_EXPIRED_BY_TIME", "1")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            filters.append(or_(Signal.expires_at.is_(None), Signal.expires_at >= now_utc_naive()))
        if str(os.getenv("ASSET_REPEAT_LOCK_REQUIRE_DELIVERED", "1")).strip().lower() in {"1", "true", "yes", "on"}:
            from db.models import SignalDelivery

            filters.append(
                sa_exists().where(
                    SignalDelivery.signal_id == Signal.signal_id,
                    SignalDelivery.sent_ok == True,
                    SignalDelivery.delivery_state.in_(
                        (
                            "sent",
                            "delivered",
                            "confirmed",
                            "SENT",
                            "CONFIRMED",
                            "RECONCILED",
                        )
                    ),
                )
            )

        async with get_session() as session:
            result = await session.execute(select(Signal.signal_id).where(and_(*filters)).limit(1))
            exists = result.scalar_one_or_none() is not None
            return exists
    except Exception as e:
        logger.warning("[signal_lock] PostgreSQL check blocked error=%s", type(e).__name__)
        return True
