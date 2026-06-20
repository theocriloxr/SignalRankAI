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


# Timeframe-specific cooldowns (CRITICAL FIX for SOLUSDT signal spam)
# 4H signals need 90+ min cooldown to prevent spam
TIMEFRAME_COOLDOWNS = {
    "4h": 90 * 60,      # 90 minutes - SOLUSDT uses this
    "1d": 6 * 60 * 60, # 6 hours
    "1h": 20 * 60,     # 20 minutes
    "15m": 10 * 60,    # 10 minutes
    "5m": 5 * 60,     # 5 minutes
    "30m": 15 * 60,    # 15 minutes
}


def get_timeframe_cooldown(timeframe: str) -> int:
    """Get cooldown seconds for a specific timeframe.
    
    CRITICAL FIX: 4H timeframe requires 90+ minute cooldown
    to prevent SOLUSDT and other 4H signals from spamming.
    """
    tf = str(timeframe).lower().strip()
    return TIMEFRAME_COOLDOWNS.get(tf, 900)  # Default 15 minutes


@dataclass
class SignalFingerprint:
    """Signal fingerprint for deduplication.
    
    CRITICAL FIX: Do NOT include entry_zone in the dedup key!
    Entry price changes every scan (SL/TP/confluence change), 
    which defeats deduplication completely.
    
    The fingerprint should identify the TRADE THESIS, not the specific targets.
    """
    asset: str
    direction: str
    timeframe: str
    entry_zone: str  # Kept for compatibility, but NOT used in to_key
    strategy_group: str
    created_at: datetime
    
    def to_key(self) -> str:
        """Generate dedup key.
        
        FIXED: Only use (asset, direction, timeframe, strategy_group)
        This identifies the trade thesis, not the changing price targets.
        
        Why this works:
        - asset + direction = what asset and which way
        - timeframe = what time horizon
        - strategy_group = what strategy generated it
        
        This prevents SOLUSDT spam while allowing genuinely
        new trade opportunities (new timeframe, new direction,
        or new strategy) to pass through.
        """
        return f"{self.asset}:{self.direction}:{self.timeframe}:{self.strategy_group}"


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
        
        # FIXED: Use fixed decimal rounding for entry zone tolerance
        # Round to 3 decimal places for crypto/forex (handles minor price drift)
        entry = round(float(signal.get("entry", 0) or 0), 3)
        
        # For high-value assets (stocks, indices), round to 2 decimals
        if entry >= 1000:
            entry = round(entry, 2)
        
        entry_zone = str(entry)  # Convert to string for consistent fingerprint
        
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
        
        # DEBUG LOGGING: Critical to verify dedup is working
        logger.info(
            f"[DEDUP CHECK] fingerprint={key} "
            f"entry_zone={fp.entry_zone} "  # Shown for debugging but NOT used in key
        )
        
        # CRITICAL FIX: Use timeframe-specific cooldown instead of fixed config
        # This prevents SOLUSDT 4H signal spam (90 min cooldown for 4H)
        timeframe = fp.timeframe
        cooldown_seconds = get_timeframe_cooldown(timeframe)
        
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
                # FIX: Use timeframe-specific cooldown_seconds
                if age < cooldown_seconds:
                    logger.debug(f"[Dedup] Duplicate in memory: {key} age={age:.0f}s cooldown={cooldown_seconds}s (tf={timeframe})")
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
                        # FIX: Use timeframe-specific cooldown_seconds
                        if age < cooldown_seconds:
                            logger.debug(f"[Dedup] Duplicate in Redis: {key} age={age:.0f}s cooldown={cooldown_seconds}s (tf={timeframe})")
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
        
        # CRITICAL: Use timeframe-specific cooldown for TTL
        tf = fp.timeframe
        cooldown_seconds = get_timeframe_cooldown(tf)
        
        # Store in memory
        self._seen_signals[key] = now
        
        # Also store in Redis for cross-process sharing
        if self._redis_client:
            try:
                redis_key = self._generate_key(fp)
                self._redis_client.set_str_sync(redis_key, str(now.timestamp()), ttl=cooldown_seconds + 60)
            except Exception as e:
                logger.debug(f"[Dedup] Redis store failed: {e}")
        
        logger.info(f"[DEDUP SAVE] fingerprint={key}")
    
    async def clear_old_entries(self) -> int:
        """Clear expired entries from memory."""
        # Use default config cooldown for cleanup
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


class MLRejectionTracker:
    """
    Tracks ML-rejected signals for adaptive learning and outcome tracking.
    
    Stores rejected signals to the database so the ML pipeline can observe
    engine-rejected candidates without waiting for decision_log backfill.
    """
    
    def __init__(self):
        self._enabled = True
    
    async def persist_rejection(
        self,
        asset: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: Any,
        ml_probability: float,
        rejection_reason: str,
        features: Optional[Dict[str, Any]] = None,
        rejection_type: str = "ml",
    ) -> bool:
        """
        Persist a rejected signal to the MLRejectedSignal table.
        
        Args:
            asset: Asset symbol (e.g., "BTCUSDT")
            timeframe: Timeframe (e.g., "1h")
            direction: "long" or "short"
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit_levels: Take profit levels (list or string)
            ml_probability: ML model probability score
            rejection_reason: Reason for rejection (e.g., "ml_filter")
            features: Signal features dict for training data
            rejection_type: Type of rejection ("ml", "engine", "score", etc.)
            
        Returns:
            True if persisted successfully, False otherwise
        """
        try:
            from db.session import get_session
            from db.models import MLRejectedSignal
            from uuid import uuid4
            
            # Handle take_profit_levels (could be list or string)
            tp_str = str(take_profit_levels) if take_profit_levels else ""
            
            async def _do_persist():
                async with get_session() as session:
                    rejection = MLRejectedSignal(
                        signal_id=str(uuid4()),
                        asset=str(asset).upper(),
                        timeframe=str(timeframe),
                        direction=str(direction).lower(),
                        entry=float(entry_price) if entry_price else 0.0,
                        stop_loss=float(stop_loss) if stop_loss else 0.0,
                        take_profit=tp_str,
                        ml_probability=float(ml_probability) if ml_probability else 0.0,
                        rejection_reason=str(rejection_reason)[:128],
                        features=dict(features) if features else {},
                        rejection_type=str(rejection_type)[:32],
                    )
                    session.add(rejection)
                    await session.commit()
            
            # Run in a new async task
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, create task
                    asyncio.create_task(_do_persist())
                    return True
                else:
                    loop.run_until_complete(_do_persist())
                    return True
            except RuntimeError:
                # No event loop, create new one
                asyncio.run(_do_persist())
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"[MLRejectionTracker] persist_rejection failed: {e}")
            return False
    
    async def get_recent_rejections(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent rejections for analysis.
        
        Args:
            hours: How many hours back to look
            limit: Maximum number of records
            
        Returns:
            List of rejection records
        """
        try:
            from db.session import get_session
            from db.models import MLRejectedSignal
            from sqlalchemy import select, desc
            from datetime import datetime, timedelta
            
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            async def _do_fetch():
                async with get_session() as session:
                    result = await session.execute(
                        select(MLRejectedSignal)
                        .where(MLRejectedSignal.created_at >= cutoff)
                        .order_by(desc(MLRejectedSignal.created_at))
                        .limit(limit)
                    )
                    rows = result.scalars().all()
                    return [
                        {
                            "id": r.id,
                            "signal_id": r.signal_id,
                            "asset": r.asset,
                            "timeframe": r.timeframe,
                            "direction": r.direction,
                            "entry": r.entry,
                            "stop_loss": r.stop_loss,
                            "take_profit": r.take_profit,
                            "ml_probability": r.ml_probability,
                            "rejection_reason": r.rejection_reason,
                            "features": r.features,
                            "actual_outcome": r.actual_outcome,
                            "created_at": r.created_at,
                        }
                        for r in rows
                    ]
            
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return asyncio.create_task(_do_fetch())
                else:
                    return loop.run_until_complete(_do_fetch())
            except RuntimeError:
                return asyncio.run(_do_fetch())
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"[MLRejectionTracker] get_recent_rejections failed: {e}")
            return []


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
