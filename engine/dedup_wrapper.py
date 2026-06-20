"""
Deduplication Wrapper - Unified dedup layer combining:
1. Existing SignalDeduplicator (in-memory/Redis)
2. New signal_lock Redis locks
3. PostgreSQL uniqueness
4. Active signal protection

Usage:
    from engine.dedup_wrapper import should_skip_signal, mark_signal_generated
    
    # Before generating a signal
    if should_skip_signal(asset, direction, timeframe, strategy_group):
        logger.info(f"Skipping duplicate: {asset} {direction} {timeframe}")
        return
    
    # After generating and storing
    mark_signal_generated(asset, direction, timeframe, strategy_group)
"""

import os
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Import existing dedup
try:
    from engine.signal_deduplicator import SignalDeduplicator
    _dedup = SignalDeduplicator()
except Exception as e:
    logger.warning(f"[dedup_wrapper] Failed to import SignalDeduplicator: {e}")
    _dedup = None

# Import new lock module
try:
    from engine.signal_lock import (
        acquire_signal_lock,
        check_signal_lock,
        check_active_signal_exists,
    )
except Exception as e:
    logger.warning(f"[dedup_wrapper] Failed to import signal_lock: {e}")
    acquire_signal_lock = None
    check_signal_lock = None
    check_active_signal_exists = None


def _get_signal_ttl_for_timeframe(timeframe: str) -> int:
    """Get TTL in seconds based on timeframe."""
    tf = str(timeframe).lower().strip()
    ttl_map = {
        "4h": 4 * 60 * 60,     # 4 hours
        "1d": 6 * 60 * 60,    # 6 hours
        "1h": 90 * 60,        # 90 minutes  
        "30m": 60 * 60,       # 60 minutes
        "15m": 30 * 60,      # 30 minutes
        "5m": 15 * 60,      # 15 minutes
    }
    return ttl_map.get(tf, 90 * 60)  # default 90 min


def should_skip_signal(
    asset: str,
    direction: str,
    timeframe: str,
    strategy_group: Optional[str] = None,
    signal_data: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """
    Check if signal should be skipped (duplicate).
    
    Returns:
        (should_skip: bool, reason: str)
    """
    asset_upper = str(asset).upper().strip()
    direction_lower = str(direction).lower().strip()
    tf = str(timeframe).lower().strip()
    
    # Check 1: Redis lock (fast path)
    if check_signal_lock is not None:
        try:
            if check_signal_lock(asset_upper, direction_lower, tf, strategy_group):
                return True, "redis_lock"
        except Exception as e:
            logger.debug(f"[dedup_wrapper] Redis lock check failed: {e}")
    
    # Check 2: Active signal exists
    if check_active_signal_exists is not None:
        try:
            if check_active_signal_exists(asset_upper, direction_lower, tf):
                return True, "active_signal_exists"
        except Exception as e:
            logger.debug(f"[dedup_wrapper] Active signal check failed: {e}")
    
    # Check 3: Existing dedup (in-memory/Redis from signal_deduplicator)
    if _dedup is not None and signal_data is not None:
        try:
            import asyncio
            
            async def _check_dedup():
                return await _dedup.is_duplicate(signal_data)
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't await in running loop from sync context
                    is_dup = False
                else:
                    is_dup = loop.run_until_complete(_check_dedup())
            except RuntimeError:
                is_dup = asyncio.run(_check_dedup())
            
            if is_dup:
                return True, "memory_duplicate"
        except Exception as e:
            logger.debug(f"[dedup_wrapper] Dedup check failed: {e}")
    
    return False, ""


def mark_signal_generated(
    asset: str,
    direction: str,
    timeframe: str,
    strategy_group: Optional[str] = None,
    signal_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Mark signal as generated (to prevent duplicates).
    
    Returns:
        True if marked successfully
    """
    asset_upper = str(asset).upper().strip()
    direction_lower = str(direction).lower().strip()
    tf = str(timeframe).lower().strip()
    
    marked = False
    
    # 1: Acquire Redis lock
    if acquire_signal_lock is not None:
        try:
            marked = acquire_signal_lock(
                asset_upper, 
                direction_lower, 
                tf, 
                strategy_group
            )
        except Exception as e:
            logger.debug(f"[dedup_wrapper] Redis lock acquire failed: {e}")
    
    # 2: Also mark in existing dedup for in-memory tracking
    if _dedup is not None and signal_data is not None:
        try:
            import asyncio
            
            async def _mark():
                await _dedup.mark_seen(signal_data)
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(_mark())
                else:
                    loop.run_until_complete(_mark())
            except RuntimeError:
                asyncio.run(_mark())
            
            marked = True
        except Exception as e:
            logger.debug(f"[dedup_wrapper] Dedup mark failed: {e}")
    
    return marked


def get_dedup_stats() -> Dict[str, Any]:
    """Get deduplication statistics."""
    stats = {
        "redis_lock": "available" if acquire_signal_lock else "unavailable",
        "active_check": "available" if check_active_signal_exists else "unavailable",
        "memory_dedup": "available" if _dedup else "unavailable",
    }
    
    if _dedup is not None:
        try:
            import asyncio
            
            async def _get():
                return await _dedup.get_duplicate_stats()
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    dedup_stats = {}
                else:
                    dedup_stats = loop.run_until_complete(_get())
            except RuntimeError:
                dedup_stats = asyncio.run(_get())
            
            stats.update(dedup_stats)
        except Exception:
            pass
    
    return stats


# ============ Batch Processing Helpers ============

def filter_duplicate_signals(signals: list[Dict[str, Any]]) -> tuple[list, list]:
    """
    Filter duplicates from a list of signals.
    
    Returns:
        (unique_signals, skipped_signals)
    """
    unique = []
    skipped = []
    
    for sig in signals:
        asset = sig.get("asset", "")
        direction = sig.get("direction", "long")
        timeframe = sig.get("timeframe", "1h")
        strategy_group = sig.get("strategy_group")
        
        should_skip, reason = should_skip_signal(
            asset, direction, timeframe, strategy_group, sig
        )
        
        if should_skip:
            logger.info(f"[dedup_wrapper] Skipping duplicate: {asset} {direction} {timeframe} reason={reason}")
            skipped.append(sig)
        else:
            unique.append(sig)
    
    return unique, skipped


def mark_signals_generated(signals: list[Dict[str, Any]]) -> int:
    """
    Mark multiple signals as generated.
    
    Returns:
        Count of successfully marked signals
    """
    marked_count = 0
    
    for sig in signals:
        asset = sig.get("asset", "")
        direction = sig.get("direction", "long")
        timeframe = sig.get("timeframe", "1h")
        strategy_group = sig.get("strategy_group")
        
        if mark_signal_generated(asset, direction, timeframe, strategy_group, sig):
            marked_count += 1
    
    return marked_count
