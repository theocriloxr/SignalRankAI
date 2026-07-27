"""Redis acceleration for proof-backed per-user same-asset cooldowns.

PostgreSQL delivery rows with ``sent_ok=True`` remain authoritative.  The
Redis key is direction agnostic because the product rule is a lock on the same
asset, regardless of whether a later candidate reverses direction.
"""

from __future__ import annotations

import logging

from services.asset_repeat_policy import (
    canonical_delivery_cooldown_key,
    get_asset_repeat_lock_hours,
    legacy_delivery_cooldown_keys,
)

logger = logging.getLogger(__name__)


def _get_cooldown_hours(tier: str) -> int:
    return int(round(get_asset_repeat_lock_hours(tier)))


def _make_delivery_key(telegram_user_id: int, asset: str, direction: str | None = None) -> str:
    del direction
    return canonical_delivery_cooldown_key(telegram_user_id, asset)


def check_delivery_cooldown(telegram_user_id: int, asset: str, direction: str = "") -> bool:
    """Return whether the Redis accelerator contains an active same-asset lock.

    Redis absence or failure returns ``False`` so the caller can continue to the
    authoritative PostgreSQL proof check instead of treating cache loss as
    durable delivery evidence.
    """

    try:
        from core.redis_state import state

        if not state.has_redis_sync():
            return False
        keys = (_make_delivery_key(telegram_user_id, asset), *legacy_delivery_cooldown_keys(telegram_user_id, asset, direction))
        for redis_key in keys:
            value = state.get_sync(redis_key)
            if value:
                logger.info(
                    "[delivery_cooldown] active user=%s asset=%s key=%s",
                    telegram_user_id,
                    str(asset).upper(),
                    redis_key,
                )
                return True
        return False
    except Exception as exc:
        logger.debug("[delivery_cooldown] Redis accelerator check failed: %s", exc)
        return False


def set_delivery_cooldown(
    telegram_user_id: int,
    asset: str,
    direction: str = "",
    tier: str = "free",
    *,
    sent_ok: bool = True,
) -> bool:
    """Set the Redis accelerator only after proven Telegram delivery."""

    if not sent_ok:
        logger.warning(
            "[delivery_cooldown] refused unproven lock user=%s asset=%s",
            telegram_user_id,
            asset,
        )
        return False
    try:
        from core.redis_state import state

        if not state.has_redis_sync():
            return False
        cooldown_hours = get_asset_repeat_lock_hours(tier)
        if cooldown_hours <= 0:
            return True
        ttl_seconds = max(1, int(cooldown_hours * 3600))
        redis_key = _make_delivery_key(telegram_user_id, asset)
        state.set_sync(redis_key, "1", ex=ttl_seconds)
        logger.info(
            "[delivery_cooldown] set user=%s asset=%s tier=%s ttl_hours=%.2f",
            telegram_user_id,
            str(asset).upper(),
            tier,
            cooldown_hours,
        )
        return True
    except Exception as exc:
        logger.debug("[delivery_cooldown] Redis accelerator set failed: %s", exc)
        return False


def clear_delivery_cooldown(telegram_user_id: int, asset: str, direction: str = "") -> bool:
    """Clear canonical and legacy Redis accelerator keys."""

    try:
        from core.redis_state import state

        if not state.has_redis_sync():
            return False
        keys = (_make_delivery_key(telegram_user_id, asset), *legacy_delivery_cooldown_keys(telegram_user_id, asset, direction))
        delete = getattr(state, "delete_sync", None)
        for key in keys:
            if callable(delete):
                delete(key)
            else:
                state.set_sync(key, "", ex=1)
        return True
    except Exception as exc:
        logger.debug("[delivery_cooldown] Redis accelerator clear failed: %s", exc)
        return False


# === Signal Generation Lock ===
# Prevents same signal being generated within timeframe window


def _make_signal_lock_key(asset: str, direction: str, timeframe: str) -> str:
    """Generate Redis key for signal generation lock.
    
    Format: signal_lock:{asset}:{direction}:{timeframe}
    Example: signal_lock:SOLUSDT:BUY:4H
    """
    asset_upper = str(asset or "").upper().strip()
    direction_upper = str(direction or "BUY").upper().strip()
    tf_upper = str(timeframe or "1H").upper().strip()
    return f"signal_lock:{asset_upper}:{direction_upper}:{tf_upper}"


def check_signal_lock(asset: str, direction: str, timeframe: str) -> bool:
    """
    Check if signal generation lock is active.
    
    Args:
        asset: Asset symbol (e.g., "SOLUSDT")
        direction: "BUY" or "SELL"
        timeframe: "4H", "1H", "15M", etc.
    
    Returns:
        True if lock is ACTIVE (skip signal generation)
        False if OK to generate
    """
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False
            
        redis_key = _make_signal_lock_key(asset, direction, timeframe)
        exists = state.get_sync(redis_key)
        
        if exists:
            logger.info(
                f"[signal_lock] SKIP asset={asset} direction={direction} "
                f"timeframe={timeframe} reason=lock_active"
            )
            return True
            
        return False
        
    except Exception as e:
        logger.debug(f"[signal_lock] check failed: {e}")
        return False


def set_signal_lock(asset: str, direction: str, timeframe: str, ttl_hours: int = 4) -> bool:
    """
    Set signal generation lock.
    
    Args:
        asset: Asset symbol
        direction: "BUY" or "SELL"
        timeframe: Timeframe
        ttl_hours: Lock duration in hours (default: 4)
    
    Returns:
        True if lock was set
    """
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False
            
        redis_key = _make_signal_lock_key(asset, direction, timeframe)
        ttl_seconds = ttl_hours * 3600
        
        state.set_sync(redis_key, "1", ex=ttl_seconds)
        
        logger.info(
            f"[signal_lock] SET asset={asset} direction={direction} "
            f"timeframe={timeframe} ttl={ttl_hours}h"
        )
        return True
        
    except Exception as e:
        logger.debug(f"[signal_lock] set failed: {e}")
        return False


def clear_signal_lock(asset: str, direction: str, timeframe: str) -> bool:
    """Clear signal generation lock."""
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False
            
        redis_key = _make_signal_lock_key(asset, direction, timeframe)
        state.set_sync(redis_key, "", ex=1)
        
        logger.info(
            f"[signal_lock] CLEAR asset={asset} direction={direction} "
            f"timeframe={timeframe}"
        )
        return True
        
    except Exception as e:
        logger.debug(f"[signal_lock] clear failed: {e}")
        return False


# === Active Signal Check (Async) ===
# Check if active signal already exists before creating new one


async def check_active_signal_exists(session, asset: str, direction: str, timeframe: str) -> bool:
    """
    Check if an active signal already exists for asset/direction/timeframe.
    
    Uses PostgreSQL to check for non-expired, non-archived signals.
    
    Args:
        session: AsyncSession
        asset: Asset symbol
        direction: "long" or "short"
        timeframe: Timeframe
    
    Returns:
        True if active signal exists (should skip generation)
    """
    try:
        from sqlalchemy import select, and_
        from db.models import Signal, Outcome
        
        # Check for active signal with same asset/direction/timeframe
        stmt = (
            select(Signal.signal_id)
            .where(
                and_(
                    Signal.asset == str(asset).upper(),
                    Signal.direction == str(direction).lower(),
                    Signal.timeframe == str(timeframe).lower(),
                    Signal.expired == False,
                    Signal.archived == False,
                )
            )
            .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
            .where(Outcome.id.is_(None))  # No outcome = still active
            .limit(1)
        )
        
        result = await session.execute(stmt)
        exists = result.scalar_one_or_none() is not None
        
        if exists:
            logger.info(
                f"[active_signal] SKIP asset={asset} direction={direction} "
                f"timeframe={timeframe} reason=active_signal_exists"
            )
            
        return exists
        
    except Exception as e:
        logger.debug(f"[active_signal] check failed: {e}")
        return False  # Fail open
