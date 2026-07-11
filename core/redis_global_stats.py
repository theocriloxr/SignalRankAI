"""
Redis-backed GlobalStats for cross-process engine metrics.

This module fixes the "Pulse showing zeros" issue by storing engine counters
in Redis instead of process-local memory. All workers (engine, scheduler, pulse reporter)
share the same Redis-backed counters.

Usage:
    from core.redis_global_stats import global_stats
    
    # In engine loop:
    global_stats.increment_scanned()
    global_stats.increment_delivered()
    global_stats.increment_vetoed("score")
    
    # In admin pulse:
    stats = global_stats.get_stats()
    # Returns: {"scanned": 150, "delivered": 3, "vetoed_score": 12, ...}
"""

import os
import time
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Redis key prefix for stats
_STATS_PREFIX = "signalrankai:global_stats:"
_STATS_KEYS = {
    "scanned": f"{_STATS_PREFIX}scanned",
    "delivered": f"{_STATS_PREFIX}delivered",
    "vetoed_regime": f"{_STATS_PREFIX}vetoed_regime",
    "vetoed_squeeze": f"{_STATS_PREFIX}vetoed_squeeze",
    "vetoed_microstructure": f"{_STATS_PREFIX}vetoed_microstructure",
    "vetoed_score": f"{_STATS_PREFIX}vetoed_score",
    "vetoed_ml": f"{_STATS_PREFIX}vetoed_ml",
    "vetoed_other": f"{_STATS_PREFIX}vetoed_other",
}


def _resolve_redis_url() -> Optional[str]:
    """Get Redis URL from environment."""
    return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None


class RedisGlobalStats:
    """
    Thread-safe global stats backed by Redis for cross-process sharing.
    
    Falls back to in-memory counters if Redis is unavailable.
    """
    
    def __init__(self):
        self._redis = None
        self._redis_url = _resolve_redis_url()
        self._has_redis = False
        
        # In-memory fallback
        self._memory: Dict[str, int] = {
            "scanned": 0,
            "delivered": 0,
            "vetoed_regime": 0,
            "vetoed_squeeze": 0,
            "vetoed_microstructure": 0,
            "vetoed_score": 0,
            "vetoed_ml": 0,
            "vetoed_other": 0,
        }
        self._lock = threading.Lock()
        
        # Try to connect to Redis
        self._init_redis()
    
    def _init_redis(self) -> None:
        """Initialize Redis connection."""
        if not self._redis_url:
            logger.debug("[global_stats] No REDIS_URL configured, using in-memory fallback")
            return
            
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                max_connections=10,
            )
            # Test connection
            self._redis.ping()
            self._has_redis = True
            logger.info("[global_stats] Connected to Redis for shared counters")
        except Exception as e:
            logger.debug(f"[global_stats] Redis unavailable, using in-memory fallback: {e}")
            self._redis = None
            self._has_redis = False
    
    def _get_redis(self):
        """Get or reconnect Redis client."""
        if self._redis is None:
            self._init_redis()
        return self._redis
    
    # ==================== Counter Methods ====================
    
    def increment_scanned(self, amount: int = 1) -> None:
        """Increment scanned counter (assets analyzed)."""
        self._increment("scanned", amount)
    
    def increment_delivered(self, amount: int = 1) -> None:
        """Increment delivered counter (signals sent to users)."""
        self._increment("delivered", amount)
    
    def increment_vetoed(self, reason: str, amount: int = 1) -> None:
        """
        Increment veto counter based on rejection reason.
        
        Args:
            reason: Type of veto - "regime", "squeeze", "microstructure", "score", "ml", "other"
        """
        reason_lower = str(reason).lower()
        
        if "regime" in reason_lower:
            key = "vetoed_regime"
        elif "squeeze" in reason_lower:
            key = "vetoed_squeeze"
        elif "microstructure" in reason_lower:
            key = "vetoed_microstructure"
        elif "score" in reason_lower or "threshold" in reason_lower:
            key = "vetoed_score"
        elif "ml" in reason_lower:
            key = "vetoed_ml"
        else:
            key = "vetoed_other"
        
        self._increment(key, amount)
    
    def _increment(self, key: str, amount: int = 1) -> None:
        """Internal increment with Redis + fallback."""
        redis_key = _STATS_KEYS.get(key)
        if not redis_key:
            return
            
        if self._has_redis and self._redis:
            try:
                self._redis.incrby(redis_key, amount)
                return
            except Exception as e:
                logger.debug(f"[global_stats] Redis increment failed: {e}")
                # Fall through to memory
        
        # In-memory fallback
        with self._lock:
            self._memory[key] = self._memory.get(key, 0) + amount
    
    def _get_value(self, key: str) -> int:
        """Get counter value from Redis or memory."""
        redis_key = _STATS_KEYS.get(key)
        if not redis_key:
            return 0
            
        if self._has_redis and self._redis:
            try:
                val = self._redis.get(redis_key)
                if val is not None:
                    return int(val)
            except Exception as e:
                logger.debug(f"[global_stats] Redis get failed: {e}")
        
        # Fallback to memory
        with self._lock:
            return self._memory.get(key, 0)
    
    # ==================== Read Methods ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get snapshot of all stats.
        
        Returns:
            Dict with scanned, delivered, and vetoed breakdowns
        """
        return {
            "scanned": self._get_value("scanned"),
            "delivered": self._get_value("delivered"),
            "vetoed_regime": self._get_value("vetoed_regime"),
            "vetoed_squeeze": self._get_value("vetoed_squeeze"),
            "vetoed_microstructure": self._get_value("vetoed_microstructure"),
            "vetoed_score": self._get_value("vetoed_score"),
            "vetoed_ml": self._get_value("vetoed_ml"),
            "vetoed_other": self._get_value("vetoed_other"),
        }
    
    def get_total_vetoed(self) -> int:
        """Get total vetoed count."""
        return (
            self._get_value("vetoed_regime") +
            self._get_value("vetoed_squeeze") +
            self._get_value("vetoed_microstructure") +
            self._get_value("vetoed_score") +
            self._get_value("vetoed_ml") +
            self._get_value("vetoed_other")
        )
    
    def get_scanned(self) -> int:
        """Get scanned counter."""
        return self._get_value("scanned")
    
    def get_delivered(self) -> int:
        """Get delivered counter."""
        return self._get_value("delivered")
    
    # ==================== Reset Methods ====================
    
    def reset(self) -> None:
        """Reset all counters to zero."""
        if self._has_redis and self._redis:
            try:
                for key in _STATS_KEYS.values():
                    self._redis.delete(key)
            except Exception as e:
                logger.debug(f"[global_stats] Redis reset failed: {e}")
        
        with self._lock:
            for key in self._memory:
                self._memory[key] = 0
    
    # ==================== Utility ====================
    
    def has_redis(self) -> bool:
        """Check if Redis is available."""
        return self._has_redis


# Global instance for easy import
global_stats = RedisGlobalStats()


# Adapter for backwards compatibility with old engine/stats_manager.py
class StatsAdapter:
    """
    Adapter class that provides stats_manager-compatible API
    while using RedisGlobalStats internally.
    """
    
    @property
    def scanned(self) -> int:
        return global_stats.get_scanned()

    @scanned.setter
    def scanned(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats.get_scanned())
        if delta:
            global_stats.increment_scanned(delta)
    
    @property
    def delivered(self) -> int:
        return global_stats.get_delivered()

    @delivered.setter
    def delivered(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats.get_delivered())
        if delta:
            global_stats.increment_delivered(delta)
    
    @property
    def vetoed_regime(self) -> int:
        return global_stats._get_value("vetoed_regime")

    @vetoed_regime.setter
    def vetoed_regime(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_regime"))
        if delta:
            global_stats._increment("vetoed_regime", delta)
    
    @property
    def vetoed_squeeze(self) -> int:
        return global_stats._get_value("vetoed_squeeze")

    @vetoed_squeeze.setter
    def vetoed_squeeze(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_squeeze"))
        if delta:
            global_stats._increment("vetoed_squeeze", delta)
    
    @property
    def vetoed_microstructure(self) -> int:
        return global_stats._get_value("vetoed_microstructure")

    @vetoed_microstructure.setter
    def vetoed_microstructure(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_microstructure"))
        if delta:
            global_stats._increment("vetoed_microstructure", delta)
    
    @property
    def vetoed_score(self) -> int:
        return global_stats._get_value("vetoed_score")

    @vetoed_score.setter
    def vetoed_score(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_score"))
        if delta:
            global_stats._increment("vetoed_score", delta)
    
    @property
    def vetoed_ml(self) -> int:
        return global_stats._get_value("vetoed_ml")

    @vetoed_ml.setter
    def vetoed_ml(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_ml"))
        if delta:
            global_stats._increment("vetoed_ml", delta)
    
    @property
    def vetoed_other(self) -> int:
        return global_stats._get_value("vetoed_other")

    @vetoed_other.setter
    def vetoed_other(self, value: int) -> None:
        delta = int(value or 0) - int(global_stats._get_value("vetoed_other"))
        if delta:
            global_stats._increment("vetoed_other", delta)
    
    def increment_scanned(self, amount: int = 1) -> None:
        global_stats.increment_scanned(amount)
    
    def increment_delivered(self, amount: int = 1) -> None:
        global_stats.increment_delivered(amount)
    
    def increment_vetoed(self, reason: str, amount: int = 1) -> None:
        global_stats.increment_vetoed(reason, amount)
    
    def get_stats(self) -> Dict[str, Any]:
        return global_stats.get_stats()
    
    def get_total_vetoed(self) -> int:
        return global_stats.get_total_vetoed()
    
    def reset(self) -> None:
        global_stats.reset()


# Legacy compatibility - stats instance like old engine/stats_manager.py
stats = StatsAdapter()
