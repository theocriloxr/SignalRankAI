"""
engine/stats_manager.py

Global statistics tracker for the engine.
Tracks activity across the entire app so the Pulse reporter can see
the numbers even when they run in different threads/tasks.

This fixes the "Total Scanned: 0" issue where local variables in 
process_assets weren't visible to the Pulse reporter.
"""

import threading
from typing import Dict, Any


class GlobalStats:
    """
    Thread-safe global stats tracker.
    
    Use these class attributes to track engine activity:
    - scanned: Total assets scanned per cycle
    - delivered: Total signals successfully delivered
    - vetoed_regime: Rejected by regime filter
    - vetoed_squeeze: Rejected by squeeze detector
    - vetoed_microstructure: Rejected by microstructure filter
    - vetoed_score: Rejected by score threshold
    - vetoed_ml: Rejected by ML filter
    - vetoed_other: Rejected by other filters
    """
    scanned: int = 0
    delivered: int = 0
    vetoed_regime: int = 0
    vetoed_squeeze: int = 0
    vetoed_microstructure: int = 0
    vetoed_score: int = 0
    vetoed_ml: int = 0
    vetoed_other: int = 0
    
    # Per-cycle breakdown for detailed reporting
    _cycle_stats: Dict[str, int] = {}
    _lock = threading.Lock()
    
    @classmethod
    def reset(cls) -> None:
        """Reset all counters to zero."""
        with cls._lock:
            cls.scanned = 0
            cls.delivered = 0
            cls.vetoed_regime = 0
            cls.vetoed_squeeze = 0
            cls.vetoed_microstructure = 0
            cls.vetoed_score = 0
            cls.vetoed_ml = 0
            cls.vetoed_other = 0
            cls._cycle_stats = {}
    
    @classmethod
    def increment_scanned(cls, amount: int = 1) -> None:
        """Increment the scanned counter."""
        with cls._lock:
            cls.scanned += amount
    
    @classmethod
    def increment_delivered(cls, amount: int = 1) -> None:
        """Increment the delivered counter."""
        with cls._lock:
            cls.delivered += amount
    
    @classmethod
    def increment_vetoed(cls, reason: str, amount: int = 1) -> None:
        """Increment the appropriate veto counter based on reason."""
        with cls._lock:
            reason_lower = str(reason).lower()
            if "regime" in reason_lower:
                cls.vetoed_regime += amount
            elif "squeeze" in reason_lower:
                cls.vetoed_squeeze += amount
            elif "microstructure" in reason_lower:
                cls.vetoed_microstructure += amount
            elif "score" in reason_lower or "threshold" in reason_lower:
                cls.vetoed_score += amount
            elif "ml" in reason_lower:
                cls.vetoed_ml += amount
            else:
                cls.vetoed_other += amount
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get a snapshot of current stats."""
        with cls._lock:
            return {
                "scanned": cls.scanned,
                "delivered": cls.delivered,
                "vetoed_regime": cls.vetoed_regime,
                "vetoed_squeeze": cls.vetoed_squeeze,
                "vetoed_microstructure": cls.vetoed_microstructure,
                "vetoed_score": cls.vetoed_score,
                "vetoed_ml": cls.vetoed_ml,
                "vetoed_other": cls.vetoed_other,
            }
    
    @classmethod
    def get_total_vetoed(cls) -> int:
        """Get total vetoed count."""
        with cls._lock:
            return (
                cls.vetoed_regime 
                + cls.vetoed_squeeze 
                + cls.vetoed_microstructure 
                + cls.vetoed_score 
                + cls.vetoed_ml 
                + cls.vetoed_other
            )


# Global instance for easy import. Prefer the Redis-backed adapter so the engine
# and admin pulse can share counters across Railway tasks/processes. Keep
# GlobalStats as a safe local fallback for tests or minimal installs.
try:
    from core.redis_global_stats import stats as stats
except Exception:
    stats = GlobalStats()
