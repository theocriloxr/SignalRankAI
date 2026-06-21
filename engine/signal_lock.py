"""
Signal Lock - Redis-based signal deduplication lock layer.

Provides distributed locking to prevent duplicate signal generation
across multiple engine instances.

Key features:
- Redis lock: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}
- TTL: 4 hours (configurable per timeframe)
- PostgreSQL uniqueness check as backup

Usage:
    from engine.signal_lock import SignalLock
    
    lock = SignalLock()
    
    # Check if signal is allowed (non-blocking)
    is_allowed = await lock.is_allowed("SOLUSDT", "BUY", "4h")
    
    # Acquire lock (blocking with timeout)
    acquired = await lock.acquire("SOLUSDT", "BUY", "4h")
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Timeframe-specific lock TTLs (in seconds)
LOCK_TTL_SECONDS = {
    "4h": 4 * 3600,      # 4 hours
    "1d": 6 * 3600,      # 6 hours
    "1h": 2 * 3600,     # 2 hours
    "15m": 60 * 60,    # 1 hour
    "5m": 30 * 60,     # 30 minutes
    "30m": 45 * 60,      # 45 minutes
}


def get_lock_ttl(timeframe: str) -> int:
    """Get TTL in seconds for a specific timeframe."""
    tf = str(timeframe).lower().strip()
    return LOCK_TTL_SECONDS.get(tf, 4 * 3600)  # Default 4 hours


def _make_lock_key(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> str:
    """Generate Redis lock key.
    
    Format: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}[:{STRATEGY_GROUP}]
    """
    asset = str(asset or "").upper().strip()
    direction = str(direction or "long").lower().strip()
    timeframe = str(timeframe or "1h").lower().strip()
    
    key = f"signal_lock:{asset}:{direction}:{timeframe}"
    
    if strategy_group:
        strategy_group = str(strategy_group).lower().strip()
        key += f":{strategy_group}"
    
    return key


async def is_signal_locked(asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
    """Check if signal is currently locked (duplicate exists).
    
    Args:
        asset: Asset symbol (e.g., "SOLUSDT")
        direction: "long" or "short"
        timeframe: Timeframe (e.g., "4h")
        strategy_group: Optional strategy group for more granular locking
    
    Returns:
        True if signal is locked (duplicate exists), False if available
    """
    key = _make_lock_key(asset, direction, timeframe, strategy_group)
    
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            result = state.get_str_sync(key)
            if result:
                logger.info(f"[signal_lock] Lock exists: {key}")
                return True
    except Exception as e:
        logger.debug(f"[signal_lock] Redis check failed: {e}")
    
# Also check PostgreSQL as backup
    try:
        exists = await active_signal_exists_for_asset(asset, direction, timeframe)
        if exists:
            logger.info(f"[signal_lock] PostgreSQL lock exists: asset={asset} tf={timeframe}")
            return True
    except Exception as e:
        logger.debug(f"[signal_lock] PostgreSQL check failed: {e}")
    
    return False


async def acquire_signal_lock(
    asset: str,
    direction: str,
    timeframe: str,
    strategy_group: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Acquire a signal lock to prevent duplicate generation.
    
    Args:
        asset: Asset symbol
        direction: "long" or "short"  
        timeframe: Timeframe
        strategy_group: Optional strategy group
        ttl_seconds: Optional custom TTL (uses default if not provided)
    
    Returns:
        True if lock acquired successfully, False if already locked
    """
    # Check if already locked first
    if await is_signal_locked(asset, direction, timeframe, strategy_group):
        logger.warning(f"[signal_lock] Failed to acquire: signal already locked for {asset} {direction} {timeframe}")
        return False
    
    key = _make_lock_key(asset, direction, timeframe, strategy_group)
    
    if ttl_seconds is None:
        ttl_seconds = get_lock_ttl(timeframe)
    
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            import time
            timestamp = str(time.time())
            state.set_str_sync(key, timestamp, ttl=ttl_seconds)
            logger.info(f"[signal_lock] Acquired: {key} TTL={ttl_seconds}s")
            return True
    except Exception as e:
        logger.error(f"[signal_lock] Redis set failed: {e}")
    
    return False


async def release_signal_lock(
    asset: str,
    direction: str,
    timeframe: str,
    strategy_group: Optional[str] = None,
) -> bool:
    """Release a signal lock.
    
    Args:
        asset: Asset symbol
        direction: "long" or "short"
        timeframe: Timeframe
        strategy_group: Optional strategy group
    
    Returns:
        True if lock released, False on error
    """
    key = _make_lock_key(asset, direction, timeframe, strategy_group)
    
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            state.delete_sync(key)
            logger.info(f"[signal_lock] Released: {key}")
            return True
    except Exception as e:
        logger.debug(f"[signal_lock] Release failed: {e}")
    
    return False


class SignalLock:
    """Signal lock manager for distributed deduplication."""
    
    def __init__(self):
        self._redis_client = None
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis client."""
        try:
            from core.redis_state import state
            if state.has_redis_sync():
                self._redis_client = state
                logger.info("[signal_lock] Using Redis for signal locking")
        except Exception as e:
            logger.debug(f"[signal_lock] Redis not available: {e}")
    
    async def is_allowed(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        """Check if signal generation is allowed (non-blocking).
        
        Args:
            asset: Asset symbol
            direction: "long" or "short"
            timeframe: Timeframe
            strategy_group: Optional strategy group
        
        Returns:
            True if signal can be generated, False if locked (duplicate)
        """
        return not await is_signal_locked(asset, direction, timeframe, strategy_group)
    
    async def try_acquire(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        """Try to acquire signal lock (non-blocking).
        
        Args:
            asset: Asset symbol
            direction: "long" or "short"
            timeframe: Timeframe
            strategy_group: Optional strategy group
        
        Returns:
            True if lock acquired, False if already locked
        """
        return await acquire_signal_lock(asset, direction, timeframe, strategy_group)
    
    async def release(self, asset: str, direction: str, timeframe: str, strategy_group: Optional[str] = None) -> bool:
        """Release signal lock.
        
        Args:
            asset: Asset symbol
            direction: "long" or "short"
            timeframe: Timeframe
            strategy_group: Optional strategy group
        
        Returns:
            True if released successfully
        """
        return await release_signal_lock(asset, direction, timeframe, strategy_group)


# Default instance
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
    from datetime import datetime, timedelta
    from sqlalchemy import select, and_
    
    try:
        from db.session import get_session
        from db.models import Signal
        
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        async with get_session() as session:
            result = await session.execute(
                select(Signal.signal_id)
                .where(
                    and_(
                        Signal.asset == str(asset).upper(),
                        Signal.direction == str(direction).lower(),
                        Signal.timeframe == str(timeframe).lower(),
                        Signal.archived == False,
                        Signal.expired == False,
                        Signal.created_at >= cutoff,
                    )
                )
                .limit(1)
            )
            exists = result.scalar_one_or_none() is not None
            return exists
    except Exception as e:
        logger.debug(f"[signal_lock] PostgreSQL check error: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test signal lock
        print("Testing SignalLock...")
        
        # Check if allowed
        allowed = await signal_lock.is_allowed("SOLUSDT", "BUY", "4h")
        print(f"Initial allowed: {allowed}")
        
        # Try to acquire
        acquired = await signal_lock.try_acquire("SOLUSDT", "BUY", "4h")
        print(f"Acquired: {acquired}")
        
        # Check again (should be locked now)
        allowed = await signal_lock.is_allowed("SOLUSDT", "BUY", "4h")
        print(f"After acquire allowed: {allowed}")
        
        # Release
        released = await signal_lock.release("SOLUSDT", "BUY", "4h")
        print(f"Released: {released}")
        
        # Check again (should be allowed now)
        allowed = await signal_lock.is_allowed("SOLUSDT", "BUY", "4h")
        print(f"After release allowed: {allowed}")
    
    asyncio.run(test())
