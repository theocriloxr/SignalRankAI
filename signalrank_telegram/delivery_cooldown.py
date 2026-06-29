"""
Delivery Cooldown - Per-user, per-asset delivery rate limiting.

Implements Redis-backed cooldown to prevent signal spam:
- Redis key: delivery:user_id:ASSET:DIRECTION
- TTL by tier:
  - VIP = 4 hours
  - Premium = 6 hours  
  - Free = 12 hours

Before sending any signal, check if cooldown key exists.
If exists, skip delivery.

Also includes:
- Signal Generation Lock (prevents same signal generated within timeframe)
- Active Signal Check (PostgreSQL check before creating new signal)
"""

import logging

logger = logging.getLogger(__name__)


def _get_cooldown_hours(tier: str) -> int:
    """Get cooldown hours by tier."""
    tier_lower = str(tier or "free").lower().strip()
    if tier_lower in ("owner", "admin", "vip"):
        return 4  # VIP: 4 hours
    elif tier_lower == "premium":
        return 6  # Premium: 6 hours
    else:
        return 12  # Free: 12 hours


def _make_delivery_key(telegram_user_id: int, asset: str, direction: str) -> str:
    """Generate Redis key for delivery cooldown.
    
    Format: delivery:{user_id}:{asset}:{direction}
    Example: delivery:123456:SOLUSDT:BUY
    """
    asset_upper = str(asset or "").upper().strip()
    direction_upper = str(direction or "BUY").upper().strip()
    return f"delivery:{int(telegram_user_id)}:{asset_upper}:{direction_upper}"


def check_delivery_cooldown(telegram_user_id: int, asset: str, direction: str) -> bool:
    """
    Check if delivery is on cooldown for user/asset/direction.
    
    Args:
        telegram_user_id: User's Telegram ID
        asset: Asset symbol (e.g., "SOLUSDT")
        direction: "BUY" or "SELL" (or "LONG"/"SHORT")
    
    Returns:
        True if cooldown is ACTIVE (should skip delivery)
        False if OK to deliver
    """
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False  # No Redis, allow delivery
            
        redis_key = _make_delivery_key(telegram_user_id, asset, direction)
        exists = state.get_sync(redis_key)
        
        if exists:
            logger.info(
                f"[delivery_cooldown] SKIP user={telegram_user_id} asset={asset} "
                f"direction={direction} reason=cooldown_active"
            )
            return True
            
        return False
        
    except Exception as e:
        logger.debug(f"[delivery_cooldown] check failed: {e}")
        return False  # Fail open - allow delivery


def set_delivery_cooldown(telegram_user_id: int, asset: str, direction: str, tier: str) -> bool:
    """
    Set delivery cooldown for user/asset/direction.
    
    Args:
        telegram_user_id: User's Telegram ID
        asset: Asset symbol (e.g., "SOLUSDT")
        direction: "BUY" or "SELL" (or "LONG"/"SHORT")
        tier: User's tier ("vip", "premium", "free")
    
    Returns:
        True if cooldown was set successfully
    """
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False
            
        redis_key = _make_delivery_key(telegram_user_id, asset, direction)
        cooldown_hours = _get_cooldown_hours(tier)
        ttl_seconds = cooldown_hours * 3600
        
        state.set_sync(redis_key, "1", ex=ttl_seconds)
        
        logger.info(
            f"[delivery_cooldown] SET user={telegram_user_id} asset={asset} "
            f"direction={direction} tier={tier} ttl={cooldown_hours}h"
        )
        return True
        
    except Exception as e:
        logger.debug(f"[delivery_cooldown] set failed: {e}")
        return False


def clear_delivery_cooldown(telegram_user_id: int, asset: str, direction: str) -> bool:
    """
    Clear delivery cooldown (e.g., when outcome is recorded).
    
    Returns:
        True if cooldown was cleared
    """
    try:
        from core.redis_state import state
        if not state.has_redis_sync():
            return False
            
        redis_key = _make_delivery_key(telegram_user_id, asset, direction)
        # Use set_sync with immediate expiry to clear
        state.set_sync(redis_key, "", ex=1)
        
        logger.info(
            f"[delivery_cooldown] CLEAR user={telegram_user_id} asset={asset} "
            f"direction={direction}"
        )
        return True
        
    except Exception as e:
        logger.debug(f"[delivery_cooldown] clear failed: {e}")
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
