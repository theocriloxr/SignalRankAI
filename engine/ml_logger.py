"""
ML Prediction Logger

Logs ML predictions to the database for drift analysis and model improvement.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def log_ml_prediction(
    session,
    signal_id: str,
    asset: str,
    timeframe: str,
    direction: str,
    ml_probability: float,
    features: Dict[str, Any],
    model_name: str = "xgboost_default",
    model_version: str = "1.0.0",
) -> bool:
    """
    Save ML prediction to database for drift analysis.
    
    Args:
        session: Database session
        signal_id: Signal UUID
        asset: Trading symbol
        timeframe: Timeframe (1h, 4h, etc.)
        direction: long or short
        ml_probability: ML model probability
        features: Raw features dict (RSI, MACD, etc.)
        model_name: Name of ML model
        model_version: Version string
        
    Returns:
        True if saved successfully
    """
    try:
        from db.models import MLShadowPrediction
        from sqlalchemy import select
        
        # Check if prediction already exists
        existing = await session.execute(
            select(MLShadowPrediction).where(
                MLShadowPrediction.signal_id == signal_id
            )
        )
        if existing.scalar_one_or_none():
            logger.debug(f"[ml_logger] Prediction already exists for {signal_id}")
            return True
        
        # Create new prediction record
        prediction = MLShadowPrediction(
            signal_id=signal_id,
            model_name=model_name,
            model_version=model_version,
            probability=float(ml_probability),
            is_shadow=True,
            feature_schema_ok=True,
            meta={
                "asset": asset,
                "timeframe": timeframe,
                "direction": direction,
                "logged_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.add(prediction)
        await session.commit()
        
        logger.info(
            f"[ml_logger] Saved ML prediction: {asset} {timeframe} {direction} "
            f"prob={ml_probability:.3f}"
        )
        return True
        
    except Exception as e:
        await session.rollback()
        logger.warning(f"[ml_logger] Failed to log ML prediction: {e}")
        return False


async def log_ml_training_data(
    session,
    signal_id: str,
    asset: str,
    timeframe: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: str,
    ml_probability: float,
    outcome_status: str,  # "win", "loss", "breakeven"
    outcome_r_multiple: Optional[float] = None,
    outcome_percent: Optional[float] = None,
    outcome_meta: Optional[Dict] = None,
    signals_created_at: Optional[datetime] = None,
    outcome_closed_at: Optional[datetime] = None,
) -> bool:
    """
    Save completed trade to ML training table for model retraining.
    
    This is called when a trade closes (TP/SL hit) so the ML model
    can learn from the actual outcome.
    
    Args:
        session: Database session
        signal_id: Signal UUID
        asset: Trading symbol
        timeframe: Timeframe
        direction: long/short
        entry: Entry price
        stop_loss: Stop loss price  
        take_profit: TP levels as JSON string
        ml_probability: Original ML probability
        outcome_status: "win", "loss", "breakeven"
        outcome_r_multiple: R-multiple achieved
        outcome_percent: P&L percentage
        outcome_meta: Additional outcome data
        signals_created_at: When signal was created
        outcome_closed_at: When trade was closed
        
    Returns:
        True if saved successfully
    """
    try:
        from db.models import MLPastTrainingData
        from sqlalchemy import select
        import json
        
        # Check if already exists
        existing = await session.execute(
            select(MLPastTrainingData).where(
                MLPastTrainingData.signal_id == signal_id
            )
        )
        if existing.scalar_one_or_none():
            logger.debug(f"[ml_logger] Training data already exists for {signal_id}")
            return True
        
        # Parse take_profit from string/dict to string
        if isinstance(take_profit, (list, dict)):
            tp_str = json.dumps(take_profit)
        else:
            tp_str = str(take_profit) if take_profit else "[]"
        
        # Calculate outcome
        if outcome_r_multiple is not None and outcome_r_multiple > 0:
            status = "win"
        elif outcome_r_multiple is not None and outcome_r_multiple < 0:
            status = "loss"
        else:
            status = outcome_status or "unknown"
        
        # Create training data record
        training_data = MLPastTrainingData(
            signal_id=signal_id,
            asset=asset,
            timeframe=timeframe,
            direction=direction,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=tp_str,
            ml_probability=float(ml_probability) if ml_probability else None,
            outcome_status=status,
            outcome_r_multiple=float(outcome_r_multiple) if outcome_r_multiple else None,
            outcome_percent=float(outcome_percent) if outcome_percent else None,
            outcome_meta=outcome_meta or {},
            signal_created_at=signals_created_at,
            outcome_closed_at=outcome_closed_at,
        )
        session.add(training_data)
        await session.commit()
        
        logger.info(
            f"[ml_logger] Saved training data: {asset} {timeframe} "
            f"outcome={status} r={outcome_r_multiple:.2f}"
        )
        return True
        
    except Exception as e:
        await session.rollback()
        logger.warning(f"[ml_logger] Failed to log training data: {e}")
        return False


async def get_training_data_count(session) -> int:
    """Get count of available training examples."""
    try:
        from db.models import MLPastTrainingData
        from sqlalchemy import select, func
        
        result = await session.execute(
            select(func.count(MLPastTrainingData.id))
        )
        return int(result.scalar() or 0)
    except Exception:
        return 0


async def get_pending_training_signals(
    session,
    limit: int = 100,
) -> list:
    """Get signals that need training data (have outcome but no training record)."""
    try:
        from db.models import Signal, Outcome, MLPastTrainingData
        from sqlalchemy import select, and_
        
        # Find signals with outcomes but no training data
        result = await session.execute(
            select(Signal)
            .join(Outcome, Outcome.signal_id == Signal.signal_id)
            .outerjoin(
                MLPastTrainingData,
                MLPastTrainingData.signal_id == Signal.signal_id
            )
            .where(
                and_(
                    MLPastTrainingData.id.is_(None),
                    Signal.ml_probability.isnot(None),
                )
            )
            .limit(limit)
        )
        return list(result.scalars().all())
    except Exception as e:
        logger.warning(f"[ml_logger] Failed to get pending signals: {e}")
        return []
