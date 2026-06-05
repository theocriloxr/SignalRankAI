"""
Strict Signal Deduplication - Task 4 Fix

Fixed deduplication logic that evaluates uniqueness STRICTLY based on:
(Asset, Timeframe, Direction) within a 12-hour lookback window.

Entry prices and timestamps are EXPLICITLY IGNORED during deduplication check
to prevent same-signal duplication from minor price ticks.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from db.models import Signal, MLRejectedSignal
from db.session import get_session
from sqlalchemy import select
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


# Configuration
LOOKBACK_HOURS = 12  # Fixed 12-hour lookback window
SIMILARITY_THRESHOLD = 0.95  # Very high threshold - only exact matches fail


class StrictSignalDedup:
    """
    Strict deduplication based on (Asset, Timeframe, Direction) ONLY.
    
    Ignores entry prices and timestamps - prevents duplicates when:
    - Same asset + same timeframe + same direction exists within 12 hours
    """
    
    @staticmethod
    def _normalize(value: Any, default: str = "") -> str:
        """Normalize text values for comparison."""
        return str(value or default).upper().strip()
    
    @staticmethod
    def _make_key(asset: str, timeframe: str, direction: str) -> str:
        """
        Create strict deduplication key from (Asset, Timeframe, Direction).
        
        Entry prices and timestamps are EXCLUDED from this key.
        """
        asset = StrictSignalDedup._normalize(asset)
        timeframe = StrictSignalDedup._normalize(timeframe).lower()
        direction = StrictSignalDedup._normalize(direction).lower()
        return f"{asset}|{timeframe}|{direction}"
    
    async def is_duplicate_strict(
        self,
        asset: str,
        timeframe: str,
        direction: str,
        lookback_hours: int = LOOKBACK_HOURS,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if signal is a duplicate based on STRICT matching.
        
        Args:
            asset: Asset ticker (e.g., "BTCUSDT")
            timeframe: Timeframe (e.g., "1h", "4h")
            direction: "long" or "short"
            lookback_hours: Lookback window (default: 12)
            
        Returns:
            (is_duplicate, existing_signal_id or None)
        """
        try:
            asset = self._normalize(asset)
            timeframe = self._normalize(timeframe).lower()
            direction = self._normalize(direction).lower()
            
            # Validate inputs
            if not asset or not timeframe or direction not in {"long", "short"}:
                return False, None
            
            # Calculate lookup window
            cutoff = now_utc_naive() - timedelta(hours=max(1, int(lookback_hours)))
            
            async with get_session() as session:
                # Query for signals with SAME asset + timeframe + direction
                # Ignore entry price - that's the key fix
                stmt = (
                    select(Signal)
                    .where(Signal.asset == asset)
                    .where(Signal.timeframe == timeframe)
                    .where(Signal.direction == direction)
                    .where(Signal.created_at >= cutoff)
                    .where(Signal.expired.is_(False))
                    .where(Signal.archived.is_(False))
                    .order_by(Signal.created_at.desc())
                    .limit(10)
                )
                
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
                
                if rows:
                    # Duplicate found - return signal_id for logging
                    existing_id = getattr(rows[0], "signal_id", None)
                    logger.info(
                        f"[dedup_strict] DUPLICATE detected: {asset} {timeframe} {direction} "
                        f"within {lookback_hours}h (existing: {existing_id})"
                    )
                    return True, existing_id
                
                return False, None
                
        except Exception as e:
            logger.warning(f"[dedup_strict] Check failed: {e}")
            return False, None
    
    async def find_duplicates_strict(
        self,
        asset: str,
        timeframe: str,
        direction: str,
        lookback_hours: int = LOOKBACK_HOURS,
    ) -> List[Dict[str, Any]]:
        """
        Find all potential duplicates for a signal.
        
        Args:
            asset: Asset ticker
            timeframe: Timeframe
            direction: "long" or "short"
            lookback_hours: Lookback window
            
        Returns:
            List of matching signal dicts
        """
        try:
            asset = self._normalize(asset)
            timeframe = self._normalize(timeframe).lower()
            direction = self._normalize(direction).lower()
            
            if not asset or not timeframe or direction not in {"long", "short"}:
                return []
            
            cutoff = now_utc_naive() - timedelta(hours=max(1, int(lookback_hours)))
            
            async with get_session() as session:
                stmt = (
                    select(Signal)
                    .where(Signal.asset == asset)
                    .where(Signal.timeframe == timeframe)
                    .where(Signal.direction == direction)
                    .where(Signal.created_at >= cutoff)
                    .where(Signal.expired.is_(False))
                    .order_by(Signal.created_at.desc())
                    .limit(50)
                )
                
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
                
                return [
                    {
                        "signal_id": getattr(r, "signal_id", None),
                        "asset": r.asset,
                        "timeframe": r.timeframe,
                        "direction": r.direction,
                        "entry": r.entry,
                        "stop_loss": r.stop_loss,
                        "take_profit": r.take_profit,
                        "score": getattr(r, "score", None),
                        "created_at": r.created_at,
                    }
                    for r in rows
                ]
                
        except Exception as e:
            logger.warning(f"[dedup_strict] Find duplicates failed: {e}")
            return []
    
    async def dedupe_batch_strict(
        self,
        signals: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate a batch of signals using STRICT matching.
        
        Keeps the highest-scoring signal for each (Asset, Timeframe, Direction) cluster.
        
        Args:
            signals: List of signal dicts
            
        Returns:
            Deduplicated signal list
        """
        if not signals:
            return []
        
        # Group by strict key
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        
        for sig in signals:
            asset = self._normalize(sig.get("asset") or sig.get("symbol"))
            timeframe = self._normalize(sig.get("timeframe") or sig.get("tf")).lower()
            direction = self._normalize(sig.get("direction") or sig.get("side") or "long").lower()
            
            key = f"{asset}|{timeframe}|{direction}"
            
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(sig)
        
        # Keep highest-scoring signal from each cluster
        deduped: List[Dict[str, Any]] = []
        
        for key, cluster in clusters.items():
            if len(cluster) == 1:
                deduped.extend(cluster)
                continue
            
            # Sort by score (descending), then by recency
            def _rank(sig: Dict[str, Any]) -> Tuple[float, float]:
                score = float(sig.get("score") or sig.get("strength") or 0.0)
                created = sig.get("created_at")
                recency = created.timestamp() if isinstance(created, datetime) else 0.0
                return (score, recency)
            
            best = max(cluster, key=_rank)
            deduped.append(best)
            
            dropped = len(cluster) - 1
            if dropped > 0:
                logger.info(
                    f"[dedup_strict] Dropped {dropped} duplicate(s) from cluster {key}"
                )
        
        return deduped


# Singleton instance
_strict_dedup = StrictSignalDedup()


async def is_signal_duplicate_strict(
    asset: str,
    timeframe: str,
    direction: str,
    lookback_hours: int = LOOKBACK_HOURS,
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function for strict duplicate checking.
    
    This is the main entry point - call this BEFORE any signal creation
    to prevent same-signal duplication.
    """
    return await _strict_dedup.is_duplicate_strict(
        asset, timeframe, direction, lookback_hours
    )


async def dedupe_signals_batch_strict(
    signals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convenience function for batch deduplication.
    """
    return await _strict_dedup.dedupe_batch_strict(signals)


__all__ = [
    "StrictSignalDedup",
    "is_signal_duplicate_strict",
    "dedupe_signals_batch_strict",
    "LOOKBACK_HOURS",
]
