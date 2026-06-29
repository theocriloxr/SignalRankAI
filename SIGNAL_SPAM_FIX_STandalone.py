"""
Signal Spam Fix - Standalone Generation Cooldown Fix

This implements a generation-level cooldown that prevents signals from being
regenerated for the same (asset, timeframe, direction) within a cooldown window.

Add this to engine/core.py or create a new middleware that wraps signal generation.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


# Configuration - Generation Cooldown
# This is SEPARATE from storage cooldown - prevents REGENERATION spam
SIGNAL_GENERATION_COOLDOWN_SECONDS = {
    "4h": 90 * 60,      # 90 minutes for 4H - fixes SOLUSDT spam
    "1d": 6 * 60 * 60, # 6 hours for daily
    "1h": 20 * 60,     # 20 minutes for 1H
    "15m": 10 * 60,   # 10 minutes for 15m
    "5m": 5 * 60,     # 5 minutes for 5m
    "30m": 15 * 60,   # 15 minutes for 30m
}

DEFAULT_GENERATION_COOLDOWN = 30 * 60  # 30 minutes default


def get_generation_cooldown(timeframe: str) -> int:
    """Get generation cooldown for a timeframe."""
    tf = str(timeframe).lower().strip()
    return SIGNAL_GENERATION_COOLDOWN_SECONDS.get(tf, DEFAULT_GENERATION_COOLDOWN)


@dataclass
class GenerationCooldown:
    """
    Tracks when signals were LAST GENERATED for each asset/timeframe/direction.
    
    This prevents the engine from generating signals too frequently
    for the same trading setup.
    """
    _last_generated: Dict[str, datetime] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    
    def _make_key(self, asset: str, timeframe: str, direction: str = "long") -> str:
        """Create a unique key for asset+timeframe+direction."""
        return f"{asset.upper()}:{timeframe.lower()}:{direction.lower()}"
    
    def can_generate(self, asset: str, timeframe: str, direction: str = "long") -> bool:
        """Check if signal can be generated for this asset/timeframe."""
        with self._lock:
            key = self._make_key(asset, timeframe, direction)
            last_gen = self._last_generated.get(key)
            
            if last_gen is None:
                return True  # Never generated before
            
            cooldown_seconds = get_generation_cooldown(timeframe)
            elapsed = (datetime.utcnow() - last_gen).total_seconds()
            
            if elapsed < cooldown_seconds:
                logger.info(
                    f"[GenCooldown] Blocked {asset} {timeframe} {direction} - "
                    f"elapsed={elapsed:.0f}s cooldown={cooldown_seconds}s"
                )
                return False
            
            return True
    
    def record_generation(self, asset: str, timeframe: str, direction: str = "long") -> None:
        """Record that a signal was generated."""
        with self._lock:
            key = self._make_key(asset, timeframe, direction)
            self._last_generated[key] = datetime.utcnow()
            logger.debug(f"[GenCooldown] Recorded generation for {key}")
    
    def get_cooldown_remaining(self, asset: str, timeframe: str, direction: str = "long") -> int:
        """Get remaining cooldown in seconds."""
        with self._lock:
            key = self._make_key(asset, timeframe, direction)
            last_gen = self._last_generated.get(key)
            
            if last_gen is None:
                return 0
            
            cooldown_seconds = get_generation_cooldown(timeframe)
            elapsed = (datetime.utcnow() - last_gen).total_seconds()
            remaining = int(cooldown_seconds - elapsed)
            return max(0, remaining)


# Global instance
generation_cooldown = GenerationCooldown()


def check_generation_cooldown(asset: str, timeframe: str, direction: str = "long") -> bool:
    """
    Main entry point - check if signal can be generated.
    
    Call this BEFORE running strategies for an asset/timeframe.
    
    Usage:
        from engine.signal_gen_cooldown import check_generation_cooldown
        
        # In the per-asset pipeline, BEFORE run_all_strategies:
        if not check_generation_cooldown(asset, timeframe):
            logger.info(f"Skipping {asset} {timeframe} - generation cooldown active")
            continue
    """
    return generation_cooldown.can_generate(asset, timeframe, direction)


def record_signal_generated(asset: str, timeframe: str, direction: str = "long") -> None:
    """
    Record that a signal was generated.
    
    Call this AFTER a signal is successfully stored/persisted.
    
    Usage:
        from engine.signal_gen_cooldown import record_signal_generated
        
        # After signal is stored:
        if signal_stored:
            record_signal_generated(asset, timeframe, direction)
    """
    generation_cooldown.record_generation(asset, timeframe, direction)


def get_generation_cooldown_remaining(asset: str, timeframe: str, direction: str = "long") -> int:
    """Get remaining cooldown in seconds."""
    return generation_cooldown.get_cooldown_remaining(asset, timeframe, direction)


if __name__ == "__main__":
    # Test the cooldown
    import asyncio
    
    async def test():
        asset = "SOLUSDT"
        timeframe = "4h"
        direction = "long"
        
        print(f"Testing generation cooldown for {asset} {timeframe}...")
        
        # First check - should be allowed
        can_gen = check_generation_cooldown(asset, timeframe, direction)
        print(f"Can generate (first check): {can_gen}")
        
        # Record a generation
        record_signal_generated(asset, timeframe, direction)
        print(f"Recorded generation")
        
        # Second check - should be blocked
        can_gen = check_generation_cooldown(asset, timeframe, direction)
        print(f"Can generate (second check): {can_gen}")
        
        # Get remaining cooldown
        remaining = get_generation_cooldown_remaining(asset, timeframe, direction)
        print(f"Remaining cooldown: {remaining}s")
        
        # Test with different timeframes
        for tf in ["5m", "15m", "1h", "4h", "1d"]:
            cooldown = get_generation_cooldown(tf)
            print(f"Timeframe {tf}: cooldown={cooldown}s ({cooldown/60:.1f}min)")
    
    asyncio.run(test())
