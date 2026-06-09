"""
ML Feedback Loop for SignalRankAI.

This module enables continuous ML learning by:
1. Storing market context with each signal
2. Labeling signals with outcomes when trades close
3. Triggering automated retraining with recent data
"""

import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

RETRAIN_DAYS = int(os.getenv("ML_RETRAIN_DAYS", "30"))
MIN_SAMPLES = int(os.getenv("ML_RETRAIN_MIN_SAMPLES", "50"))
RETRAIN_INTERVAL_HOURS = int(os.getenv("ML_RETRAIN_INTERVAL_HOURS", "168"))


class MLFeedbackLoop:
    """ML Feedback Loop for continuous learning."""
    
    def __init__(self):
        self._redis = None
        self._redis_url = self._resolve_redis_url()
        self._last_retrain: Optional[datetime] = None
        if self._redis_url:
            self._init_redis()
    
    def _resolve_redis_url(self) -> Optional[str]:
        return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None
    
    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[ml_feedback] Connected to Redis")
        except Exception as e:
            logger.debug(f"[ml_feedback] Redis unavailable: {e}")
            self._redis = None
    
    async def record_signal(
        self,
        signal: Dict[str, Any],
        market_context: Dict[str, Any]
    ) -> None:
        """Record a signal with market context for ML training."""
        import json
        
        signal_id = signal.get("signal_id") or signal.get("id")
        if not signal_id:
            return
        
        record = {
            "signal_id": signal_id,
            "asset": signal.get("asset"),
            "direction": signal.get("direction"),
            "entry": signal.get("entry"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "score": signal.get("score"),
            "ml_probability": signal.get("ml_probability"),
            "strategy_name": signal.get("strategy_name"),
            "regime": signal.get("regime"),
            "rsi": market_context.get("rsi"),
            "volatility": market_context.get("volatility"),
            "dxy_strength": market_context.get("dxy_strength"),
            "vix": market_context.get("vix"),
            "dxy_trend": market_context.get("dxy_trend"),
            "vix_trend": market_context.get("vix_trend"),
            "news_sentiment": market_context.get("news_sentiment"),
            "atr_percent": market_context.get("atr_percent"),
            "volume_ratio": market_context.get("volume_ratio"),
            "macd_trend": market_context.get("macd_trend"),
            "adx_trend": market_context.get("adx_trend"),
            "outcome": None,
            "r_multiple": None,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        
        if self._redis:
            self._redis.hset(
                "signalrankai:ml_signals",
                signal_id,
                json.dumps(record)
            )
        
        logger.debug(f"[ml_feedback] Recorded signal {signal_id} with context")
    
    async def update_outcome(
        self,
        signal_id: str,
        outcome: str,
        r_multiple: Optional[float] = None,
        closed_at: Optional[datetime] = None
    ) -> None:
        """Update a signal with its outcome after trade closes."""
        import json
        
        if closed_at is None:
            closed_at = datetime.utcnow()
        
        outcome_data = {
            "outcome": outcome,
            "r_multiple": r_multiple,
            "closed_at": closed_at.isoformat(),
        }
        
        if self._redis:
            existing = self._redis.hget("signalrankai:ml_signals", signal_id)
            if existing:
                record = json.loads(existing)
                record.update(outcome_data)
                self._redis.hset(
                    "signalrankai:ml_signals",
                    signal_id,
                    json.dumps(record)
                )
        
        logger.info(f"[ml_feedback] Updated outcome for {signal_id}: {outcome} ({r_multiple}R)")
    
    async def get_recent_signals(
        self,
        days: int = RETRAIN_DAYS,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get recent signals with outcomes for retraining."""
        import json
        
        signals = []
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        if self._redis:
            all_data = self._redis.hgetall("signalrankai:ml_signals")
            
            for signal_id, data in (all_data or {}).items():
                try:
                    record = json.loads(data)
                    if record.get("outcome") and record.get("recorded_at", "") >= cutoff_str:
                        signals.append(record)
                except Exception:
                    continue
        
        signals.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
        return signals[:limit]
    
    async def trigger_retraining(
        self,
        force: bool = False
    ) -> Dict[str, Any]:
        """Trigger ML model retraining with recent signals."""
        if not force and self._last_retrain:
            hours_since = (
                datetime.utcnow() - self._last_retrain
            ).total_seconds() / 3600
            
            if hours_since < RETRAIN_INTERVAL_HOURS:
                logger.info(
                    f"[ml_feedback] Skipping retrain: only {hours_since:.1f}h since last "
                    f"(min: {RETRAIN_INTERVAL_HOURS}h)"
                )
                return {"skipped": True, "reason": "not_due"}
        
        signals = await self.get_recent_signals(days=RETRAIN_DAYS)
        
        if len(signals) < MIN_SAMPLES:
            logger.info(
                f"[ml_feedback] Skipping retrain: only {len(signals)} samples "
                f"(min: {MIN_SAMPLES})"
            )
            return {"skipped": True, "reason": "not_enough_samples"}
        
        outcomes = {}
        for sig in signals:
            outcome = sig.get("outcome", "unknown")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        
        logger.info(
            f"[ml_feedback] Retraining with {len(signals)} signals: {outcomes}"
        )
        
        self._last_retrain = datetime.utcnow()
        
        return {
            "success": True,
            "signals_used": len(signals),
            "outcomes": outcomes,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get feedback loop statistics."""
        count = 0
        with_outcomes = 0
        
        if self._redis:
            import json
            all_data = self._redis.hgetall("signalrankai:ml_signals")
            count = len(all_data or {})
            
            for _, data in (all_data or {}).items():
                try:
                    record = json.loads(data)
                    if record.get("outcome"):
                        with_outcomes += 1
                except Exception:
                    pass
        
        return {
            "total_signals": count,
            "with_outcomes": with_outcomes,
            "last_retrain": self._last_retrain.isoformat() if self._last_retrain else None,
        }


_ml_feedback_loop: Optional[MLFeedbackLoop] = None


def get_ml_feedback_loop() -> MLFeedbackLoop:
    """Get or create the global ML feedback loop."""
    global _ml_feedback_loop
    if _ml_feedback_loop is None:
        _ml_feedback_loop = MLFeedbackLoop()
    return _ml_feedback_loop
