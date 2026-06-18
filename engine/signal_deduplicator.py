"""
Signal Deduplicator - Enhanced Version

This module provides:
- Improved signal deduplication logic
- Fresh signal handling (allows new signals through cooldown)
- Configurable cooldown periods
- Redis-backed deduplication state

Usage:
    from engine.signal_deduplicator import SignalDeduplicator
    
    dedup = SignalDeduplicator()
    is_duplicate = await dedup.is_duplicate(signal)
    await dedup.mark_seen(signal)
"""

import os
import hashlib
import logging
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class SignalFingerprint:
    """Signal fingerprint for deduplication."""
    asset: str
    direction: str
    timeframe: str
    entry_zone: str  # Entry price zone (rounded)
    strategy_group: str
    created_at: datetime
    
    def to_key(self) -> str:
        """Generate dedup key."""
        return f"{self.asset}:{self.direction}:{self.timeframe}:{self.entry_zone}"


@dataclass
class DedupConfig:
    """Deduplication configuration."""
    cooldown_seconds: int = 900  # 15 min default
    entry_zone_tolerance: float = 0.002  # 0.2% entry price tolerance
    allow_fresh_breakthrough: bool = True  # Allow high-quality fresh signals
    min_score_for_breakthrough: float = 85.0  # Score threshold for breakthrough
    max_age_for_breakthrough_hours: int = 2  # Max age for breakthrough


class SignalDeduplicator:
    """
    Enhanced signal deduplication with configurable policies.
    
    Features:
    - Fingerprint-based dedup (not just exact match)
    - Entry zone tolerance (nearby entries treated as same)
    - Fresh signal breakthrough (high quality signals bypass cooldown)
    - Redis-backed state for cross-process sharing
    - Configurable cooldown periods
    """
    
    def __init__(self, config: Optional[DedupConfig] = None):
        self.config = config or DedupConfig()
        self._seen_signals: Dict[str, datetime] = {}
        self._redis_client = None
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis client if available."""
        try:
            from core.redis_state import state
            if state.has_redis_sync():
                self._redis_client = state
                logger.info("[Dedup] Using Redis for dedup state")
        except Exception as e:
            logger.debug(f"[Dedup] Redis not available: {e}")
    
    def _generate_fingerprint(self, signal: Dict[str, Any]) -> SignalFingerprint:
        """Generate fingerprint from signal."""
        asset = str(signal.get("asset", "")).upper()
        direction = str(signal.get("direction", "long")).lower()
        timeframe = str(signal.get("timeframe", "1h")).lower()
        
        # Calculate entry zone (rounded to tolerance)
        entry = float(signal.get("entry", 0) or 0)
        if entry > 0:
            zone_size = entry * self.config.entry_zone_tolerance
            entry_zone = round(entry / zone_size) * zone_size
        else:
            entry_zone = 0.0
        
        # Strategy group
        strategy = signal.get("strategy_name", "")
        strategy_group = strategy.split("_")[0] if strategy else "unknown"
        
        return SignalFingerprint(
            asset=asset,
            direction=direction,
            timeframe=timeframe,
            entry_zone=entry_zone,
            strategy_group=strategy_group,
            created_at=datetime.utcnow()
        )
    
    def _generate_key(self, fp: SignalFingerprint) -> str:
        """Generate Redis key."""
        return f"dedup:signal:{fp.to_key()}"
    
    async def is_duplicate(self, signal: Dict[str, Any]) -> bool:
        """Check if signal is duplicate."""
        fp = self._generate_fingerprint(signal)
        key = fp.to_key()
        
        # Check breakthrough conditions first (fresh signals get priority)
        if self.config.allow_fresh_breakthrough:
            score = float(signal.get("score", 0) or 0)
            if score >= self.config.min_score_for_breakthrough:
                # Check if this is a significantly newer signal
                if await self._is_fresh_breakthrough(signal):
                    logger.info(f"[Dedup] Fresh breakthrough for {key}: score={score}")
                    return False
        
        # Check in-memory cache
        if key in self._seen_signals:
            created = self._seen_signals.get(key)
            if created:
                age = (datetime.utcnow() - created).total_seconds()
                if age < self.config.cooldown_seconds:
                    logger.debug(f"[Dedup] Duplicate in memory: {key} age={age:.0f}s")
                    return True
        
        # Check Redis if available
        if self._redis_client:
            try:
                redis_key = self._generate_key(fp)
                last_seen = self._redis_client.get_str_sync(redis_key)
                if last_seen:
                    try:
                        ts = float(last_seen)
                        age = time.time() - ts
                        if age < self.config.cooldown_seconds:
                            logger.debug(f"[Dedup] Duplicate in Redis: {key} age={age:.0f}s")
                            return True
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[Dedup] Redis check failed: {e}")
        
        return False
    
    async def _is_fresh_breakthrough(self, signal: Dict[str, Any]) -> bool:
        """Check if signal qualifies for fresh breakthrough."""
        try:
            # Get signal timestamp
            sig_time = signal.get("created_at") or signal.get("signal_created_at")
            if sig_time:
                if isinstance(sig_time, str):
                    sig_time = datetime.fromisoformat(sig_time.replace("Z", "+00:00"))
                age = (datetime.utcnow() - sig_time).total_seconds() / 3600  # hours
                
                if age < self.config.max_age_for_breakthrough_hours:
                    return True
            
            # Also check score freshness
            score = float(signal.get("score", 0) or 0)
            if score >= self.config.min_score_for_breakthrough:
                # Fresh high-scoring signal - allow through cooldown
                return True
                
        except Exception as e:
            logger.debug(f"[Dedup] Fresh check error: {e}")
        
        return False
    
    async def mark_seen(self, signal: Dict[str, Any]) -> None:
        """Mark signal as seen."""
        fp = self._generate_fingerprint(signal)
        key = fp.to_key()
        now = datetime.utcnow()
        
        # Store in memory
        self._seen_signals[key] = now
        
        # Also store in Redis for cross-process sharing
        if self._redis_client:
            try:
                redis_key = self._generate_key(fp)
                self._redis_client.set_str_sync(redis_key, str(now.timestamp()), ttl=self.config.cooldown_seconds + 60)
            except Exception as e:
                logger.debug(f"[Dedup] Redis store failed: {e}")
        
        logger.debug(f"[Dedup] Marked seen: {key}")
    
    async def clear_old_entries(self) -> int:
        """Clear expired entries from memory."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.config.cooldown_seconds)
        to_remove = []
        
        for key, created in self._seen_signals.items():
            if created < cutoff:
                to_remove.append(key)
        
        for key in to_remove:
            self._seen_signals.pop(key, None)
        
        if to_remove:
            logger.debug(f"[Dedup] Cleared {len(to_remove)} expired entries")
        
        return len(to_remove)
    
    async def get_duplicate_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        now = datetime.utcnow()
        active_count = 0
        expired_count = 0
        
        for key, created in self._seen_signals.items():
            age = (now - created).total_seconds()
            if age < self.config.cooldown_seconds:
                active_count += 1
            else:
                expired_count += 1
        
        return {
            "active_signals": active_count,
            "expired_signals": expired_count,
            "cooldown_seconds": self.config.cooldown_seconds,
            "breakthrough_enabled": self.config.allow_fresh_breakthrough,
            "breakthrough_score": self.config.min_score_for_breakthrough
        }


class StrictSignalDedup:
    """
    Strict deduplication - only exact matches.
    Use for preventing spam, not for quality.
    """
    
    def __init__(self):
        self._seen: Set[str] = set()
    
    def is_duplicate(self, signal: Dict[str, Any]) -> bool:
        """Check exact duplicate."""
        key = self._generate_exact_key(signal)
        return key in self._seen
    
    def mark_seen(self, signal: Dict[str, Any]) -> None:
        """Mark as seen."""
        key = self._generate_exact_key(signal)
        self._seen.add(key)
    
    def _generate_exact_key(self, signal: Dict[str, Any]) -> str:
        """Generate exact match key."""
        return f"{signal.get('asset')}:{signal.get('direction')}:{signal.get('timeframe')}:{signal.get('entry')}"


# Default instance
default_dedup = SignalDeduplicator()


# Helper functions
async def is_signal_duplicate(signal: Dict[str, Any]) -> bool:
    """Check if signal is duplicate using default dedup."""
    return await default_dedup.is_duplicate(signal)


async def mark_signal_seen(signal: Dict[str, Any]) -> None:
    """Mark signal as seen using default dedup."""
    await default_dedup.mark_seen(signal)


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        dedup = SignalDeduplicator()
        
        test_signal = {
            "asset": "BTCUSDT",
            "direction": "long",
            "timeframe": "1h",
            "entry": 45000.0,
            "score": 88.0,
            "created_at": datetime.utcnow()
        }
        
        # Test fingerprint generation
        fp = dedup._generate_fingerprint(test_signal)
        print(f"Fingerprint: {fp.to_key()}")
        
        # Test duplicate check
        is_dup = await dedup.is_duplicate(test_signal)
        print(f"First check (should be False): {is_dup}")
        
        # Mark as seen
        await dedup.mark_seen(test_signal)
        
        # Check again
        is_dup = await dedup.is_duplicate(test_signal)
        print(f"Second check (should be True): {is_dup}")
        
        # Get stats
        stats = await dedup.get_duplicate_stats()
        print(f"Stats: {stats}")
    
    asyncio.run(test())
