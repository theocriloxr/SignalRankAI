"""
Historical Similarity Engine for Signal Quality Assurance.

Compares new signals against historical setups to predict performance.
Uses multiple factors to determine similarity and calculate win probability.

Signal Generated
       ↓
Virtual Test Engine
       ↓
Risk Validation
       ↓
Historical Similarity Check
       ↓
User Delivery
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from utils.async_runner import run_sync
from db.session import get_session

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or str(default))
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


# Configuration
SIMILARITY_ENABLED = _env_bool("HISTORICAL_SIMILARITY_ENABLED", True)
MIN_SIMILAR_SIGNALS = _env_float("MIN_SIMILAR_SIGNALS", 5.0)
SIMILARITY_WEIGHT = _env_float("SIMILARITY_WEIGHT", 0.25)
MIN_SIMILARITY_SCORE = _env_float("MIN_SIMILARITY_SCORE", 0.35)


def calculate_similarity_score(
    current_signal: Dict[str, Any],
    historical_signals: List[Dict[str, Any]]
) -> Tuple[float, int, Dict[str, Any]]:
    """
    Calculate similarity score between current signal and historical ones.
    
    Args:
        current_signal: The signal to evaluate
        historical_signals: List of historical signals with outcomes
        
    Returns:
        Tuple of (similarity_score, similar_count, breakdown_dict)
    """
    if not historical_signals:
        return 0.0, 0, {}
    
    similar_count = 0
    total_similarity = 0.0
    wins_in_similar = 0
    
    breakdown = {
        "asset_match": 0.0,
        "direction_match": 0.0,
        "timeframe_match": 0.0,
        "regime_match": 0.0,
        "strategy_match": 0.0,
    }
    
    current_asset = (current_signal.get("asset") or "").upper()
    current_direction = (current_signal.get("direction") or "").lower()
    current_timeframe = current_signal.get("timeframe") or "1h"
    current_regime = current_signal.get("regime") or "unknown"
    current_strategy = current_signal.get("strategy_name") or ""
    
    for hist in historical_signals:
        similarity = 0.0
        factors = 0
        
        # Asset match (30% weight)
        hist_asset = (hist.get("asset") or "").upper()
        if hist_asset == current_asset:
            similarity += 0.30
            breakdown["asset_match"] += 0.30
        factors += 1
        
        # Direction match (20% weight)
        hist_direction = (hist.get("direction") or "").lower()
        if hist_direction == current_direction:
            similarity += 0.20
            breakdown["direction_match"] += 0.20
        factors += 1
        
        # Timeframe match (15% weight)
        hist_timeframe = hist.get("timeframe") or "1h"
        if hist_timeframe == current_timeframe:
            similarity += 0.15
            breakdown["timeframe_match"] += 0.15
        factors += 1
        
        # Regime match (20% weight)
        hist_regime = hist.get("regime") or "unknown"
        if hist_regime == current_regime and current_regime != "unknown":
            similarity += 0.20
            breakdown["regime_match"] += 0.20
        factors += 1
        
        # Strategy match (15% weight)
        hist_strategy = hist.get("strategy_name") or ""
        if hist_strategy == current_strategy and current_strategy:
            similarity += 0.15
            breakdown["strategy_match"] += 0.15
        factors += 1
        
        # Consider similar if > 60% match
        if similarity >= 0.60:
            similar_count += 1
            total_similarity += similarity
            
            # Count wins
            outcome = (hist.get("outcome_status") or hist.get("status") or "").lower()
            if outcome in ("tp", "win", "take_profit", "profit"):
                wins_in_similar += 1
    
    if similar_count == 0:
        return 0.0, 0, breakdown
    
    avg_similarity = total_similarity / similar_count
    win_rate = wins_in_similar / similar_count if similar_count > 0 else 0.0
    
    return avg_similarity, similar_count, breakdown


async def check_historical_similarity(
    signal: Dict[str, Any],
    max_age_days: int = 180
) -> Tuple[bool, float, int, str]:
    """
    Check if similar historical signals performed well.
    
    Args:
        signal: Current signal to check
        max_age_days: How far back to look for historical signals
        
    Returns:
        Tuple of (should_pass, similarity_score, similar_count, reason)
    """
    if not SIMILARITY_ENABLED:
        return True, 0.0, 0, "similarity_disabled"
    
    asset = signal.get("asset") or ""
    direction = signal.get("direction") or "long"
    timeframe = signal.get("timeframe") or "1h"
    
    if not asset:
        return True, 0.0, 0, "no_asset"
    
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        
        async with get_session() as session:
            # Fetch historical signals for this asset
            from sqlalchemy import select, and_
            
            query = (
                select(Signal, Outcome)
                .join(Outcome, Signal.signal_id == Outcome.signal_id, isouter=True)
                .where(
                    Signal.asset == asset,
                    Signal.timeframe == timeframe,
                    Signal.direction == direction,
                    Signal.created_at >= cutoff_date,
                    Signal.status.in_(["closed", "expired"]),
                )
                .order_by(Signal.created_at.desc())
                .limit(200)
            )
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            if not rows:
                # No history - allow signal but note it
                return True, 0.0, 0, "no_history"
            
            historical_signals = []
            for row in rows:
                sig = row[0]
                outcome = row[1]
                
                historical_signals.append({
                    "asset": sig.asset,
                    "direction": sig.direction,
                    "timeframe": sig.timeframe,
                    "regime": sig.regime,
                    "strategy_name": sig.strategy_name,
                    "outcome_status": outcome.status if outcome else None,
                    "created_at": sig.created_at,
                })
            
            # Calculate similarity
            similarity_score, similar_count, breakdown = calculate_similarity_score(
                signal, historical_signals
            )
            
            if similar_count < MIN_SIMILAR_SIGNALS:
                reason = f"insufficient_history ({similar_count} < {MIN_SIMILAR_SIGNALS})"
                return True, similarity_score, similar_count, reason
            
            if similarity_score < MIN_SIMILARITY_SCORE:
                reason = f"poor_similarity ({similarity_score:.2f} < {MIN_SIMILARITY_SCORE})"
                return False, similarity_score, similar_count, reason
            
            return True, similarity_score, similar_count, "passed"
    
    except Exception as e:
        logger.debug(f"[similarity] Check failed: {e}")
        return True, 0.0, 0, f"error: {str(e)[:50]}"


def check_historical_similarity_sync(
    signal: Dict[str, Any],
    max_age_days: int = 180
) -> Tuple[bool, float, int, str]:
    """Synchronous wrapper for historical similarity check."""
    try:
        return run_sync(check_historical_similarity(signal, max_age_days))
    except Exception as e:
        logger.debug(f"[similarity] Sync check failed: {e}")
        return True, 0.0, 0, f"error: {str(e)[:50]}"


async def get_historical_winrate(
    asset: str,
    direction: str = "long",
    timeframe: str = "1h",
    regime: str = None,
    max_age_days: int = 180
) -> Tuple[float, int, int]:
    """
    Get historical win rate for a specific setup.
    
    Args:
        asset: Asset symbol
        direction: long/short
        timeframe: Timeframe
        regime: Market regime (optional)
        max_age_days: How far back to look
        
    Returns:
        Tuple of (win_rate, total_signals, wins)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        from sqlalchemy import select, and_, func
        
        async with get_session() as session:
            conditions = [
                Signal.asset == asset,
                Signal.direction == direction,
                Signal.timeframe == timeframe,
                Signal.created_at >= cutoff_date,
                Signal.status.in_(["closed", "expired"]),
            ]
            
            if regime:
                conditions.append(Signal.regime == regime)
            
            # Total count
            total_query = (
                select(func.count(Signal.signal_id))
                .where(and_(*conditions))
            )
            total_result = await session.execute(total_query)
            total_signals = total_result.scalar() or 0
            
            if total_signals == 0:
                return 0.0, 0, 0
            
            # Win count
            win_query = (
                select(func.count(Signal.signal_id))
                .join(Outcome, Signal.signal_id == Outcome.signal_id)
                .where(
                    and_(*conditions),
                    Outcome.status.in_(["tp", "win", "take_profit"]),
                )
            )
            win_result = await session.execute(win_query)
            wins = win_result.scalar() or 0
            
            win_rate = wins / total_signals if total_signals > 0 else 0.0
            
            return win_rate, total_signals, wins
    
    except Exception as e:
        logger.debug(f"[similarity] Win rate query failed: {e}")
        return 0.0, 0, 0


def get_historical_winrate_sync(
    asset: str,
    direction: str = "long",
    timeframe: str = "1h",
    regime: str = None,
    max_age_days: int = 180
) -> Tuple[float, int, int]:
    """Synchronous wrapper for historical win rate."""
    try:
        return run_sync(get_historical_winrate(
            asset, direction, timeframe, regime, max_age_days
        ))
    except Exception as e:
        logger.debug(f"[similarity] Win rate sync failed: {e}")
        return 0.0, 0, 0


async def get_similar_signals(
    signal: Dict[str, Any],
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Find similar historical signals for reference.
    
    Args:
        signal: Current signal
        limit: Max results to return
        
    Returns:
        List of similar historical signals
    """
    asset = signal.get("asset") or ""
    direction = signal.get("direction") or "long"
    timeframe = signal.get("timeframe") or "1h"
    regime = signal.get("regime") or None
    strategy = signal.get("strategy_name") or ""
    
    if not asset:
        return []
    
    cutoff_date = datetime.utcnow() - timedelta(days=180)
    
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        from sqlalchemy import select, and_
        
        async with get_session() as session:
            # Build query
            conditions = [
                Signal.asset == asset,
                Signal.created_at >= cutoff_date,
                Signal.status.in_(["closed", "expired"]),
            ]
            
            if direction:
                conditions.append(Signal.direction == direction)
            if timeframe:
                conditions.append(Signal.timeframe == timeframe)
            if regime:
                conditions.append(Signal.regime == regime)
            if strategy:
                conditions.append(Signal.strategy_name == strategy)
            
            query = (
                select(Signal, Outcome)
                .join(Outcome, Signal.signal_id == Outcome.signal_id, isouter=True)
                .where(and_(*conditions))
                .order_by(Signal.created_at.desc())
                .limit(limit)
            )
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            similar = []
            for row in rows:
                sig = row[0]
                outcome = row[1]
                
                similar.append({
                    "signal_id": sig.signal_id,
                    "asset": sig.asset,
                    "direction": sig.direction,
                    "timeframe": sig.timeframe,
                    "entry": sig.entry,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                    "score": sig.score,
                    "regime": sig.regime,
                    "strategy_name": sig.strategy_name,
                    "outcome": outcome.status if outcome else None,
                    "r_multiple": outcome.r_multiple if outcome else None,
                    "created_at": sig.created_at.isoformat() if sig.created_at else None,
                    "closed_at": outcome.closed_at.isoformat() if outcome and outcome.closed_at else None,
                })
            
            return similar
    
    except Exception as e:
        logger.debug(f"[similarity] Similar signals query failed: {e}")
        return []


def get_similar_signals_sync(
    signal: Dict[str, Any],
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for similar signals."""
    try:
        return run_sync(get_similar_signals(signal, limit))
    except Exception as e:
        logger.debug(f"[similarity] Similar signals sync failed: {e}")
        return []


class SimilarityEngine:
    """Main similarity engine class for external access."""
    
    def __init__(self):
        self.enabled = SIMILARITY_ENABLED
        self.min_similar = MIN_SIMILAR_SIGNALS
        self.min_score = MIN_SIMILARITY_SCORE
    
    def check(self, signal: Dict[str, Any]) -> Tuple[bool, float, int, str]:
        """Check signal against historical data."""
        return check_historical_similarity_sync(signal)
    
    def get_win_rate(
        self,
        asset: str,
        direction: str = "long",
        timeframe: str = "1h",
        regime: str = None
    ) -> Tuple[float, int, int]:
        """Get historical win rate."""
        return get_historical_winrate_sync(asset, direction, timeframe, regime)
    
    def get_similar(self, signal: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
        """Get similar historical signals."""
        return get_similar_signals_sync(signal, limit)


# Singleton instance
_similarity_engine: SimilarityEngine | None = None


def get_similarity_engine() -> SimilarityEngine:
    """Get the similarity engine singleton."""
    global _similarity_engine
    if _similarity_engine is None:
        _similarity_engine = SimilarityEngine()
    return _similarity_engine
