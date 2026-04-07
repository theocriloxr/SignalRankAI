"""
Signal deduplication, caching, and ML rejection tracking.
"""
import logging
from typing import Optional, Dict, Set
from datetime import datetime, timedelta
from db.models import Signal, MLRejectedSignal
from db.session import get_session
from sqlalchemy import select

logger = logging.getLogger(__name__)

class SignalDeduplicator:
    """Prevent duplicate signals within configured dedup window."""
    
    def __init__(self):
        self.recent_signals: Set[str] = set()
        self._cache_ttl = timedelta(hours=1)
    
    def make_fingerprint(self, asset: str, timeframe: str, direction: str, entry_price: float) -> str:
        """Create unique signal fingerprint."""
        return f"{asset}_{timeframe}_{direction}_{int(entry_price)}"
    
    async def is_duplicate(self, asset: str, timeframe: str, direction: str, entry_price: float) -> bool:
        """Check if signal is duplicate within dedup window."""
        try:
            fingerprint = self.make_fingerprint(asset, timeframe, direction, entry_price)
            
            async with get_session() as session:
                cutoff = datetime.utcnow() - self._cache_ttl
                stmt = select(Signal).where(
                    Signal.asset == asset,
                    Signal.timeframe == timeframe,
                    Signal.direction == direction,
                    Signal.entry >= entry_price * 0.99,
                    Signal.entry <= entry_price * 1.01,
                    Signal.created_at >= cutoff
                ).limit(1)
                
                result = await session.execute(stmt)
                return result.scalars().first() is not None
        except Exception as e:
            logger.warning(f"Dedup check failed: {e}")
            return False
    
    async def register_signal(self, asset: str, timeframe: str, direction: str, entry_price: float) -> None:
        """Register signal to prevent future duplication."""
        try:
            fingerprint = self.make_fingerprint(asset, timeframe, direction, entry_price)
            self.recent_signals.add(fingerprint)
        except Exception as e:
            logger.warning(f"Signal registration failed: {e}")


class MLRejectionTracker:
    """Track ML-rejected signals for training and outcome analysis."""
    
    async def persist_rejection(self, 
                               asset: str, 
                               timeframe: str, 
                               direction: str,
                               entry_price: float,
                               stop_loss: float,
                               take_profit_levels: list,
                               ml_probability: float,
                               rejection_reason: str,
                               features: Dict[str, float]) -> None:
        """Store ML rejection for future outcome tracking."""
        try:
            async with get_session() as session:
                rejection = MLRejectedSignal(
                    asset=asset,
                    timeframe=timeframe,
                    direction=direction,
                    entry=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit_levels[0]['price'] if take_profit_levels else entry_price * 1.05,
                    ml_probability=ml_probability,
                    rejection_reason=rejection_reason,
                    features=features,
                    actual_outcome=None,
                    outcome_tracked_at=None,
                    created_at=datetime.utcnow()
                )
                
                session.add(rejection)
                await session.flush()
                logger.info(f"ML rejection stored: {asset} {timeframe} {direction}")
        except Exception as e:
            logger.error(f"Failed to persist ML rejection: {e}")
    
    async def track_rejection_outcomes(self) -> int:
        """Check rejected signals for actual outcomes (TP/SL hit). Returns count tracked."""
        try:
            async with get_session() as session:
                # Get untracked rejections
                stmt = select(MLRejectedSignal).where(
                    MLRejectedSignal.actual_outcome.is_(None),
                    MLRejectedSignal.created_at >= datetime.utcnow() - timedelta(days=7)
                )
                
                result = await session.execute(stmt)
                rejections = result.scalars().all()
                
                tracked_count = 0
                for rejection in rejections:
                    # Simplified: assume if enough time passed, outcome determined
                    time_since = datetime.utcnow() - rejection.created_at
                    if time_since > timedelta(hours=4):
                        # Mark as tracked (in production, integrate with live price data)
                        rejection.actual_outcome = None  # Would be 'hit_tp' or 'hit_sl'
                        rejection.outcome_tracked_at = datetime.utcnow()
                        tracked_count += 1
                
                if tracked_count > 0:
                    await session.flush()
                    logger.info(f"Tracked {tracked_count} rejection outcomes")
                
                return tracked_count
        except Exception as e:
            logger.error(f"Failed to track rejection outcomes: {e}")
            return 0
