"""
ML-Driven Dynamic Position Sizing for SignalRankAI.

Instead of suggesting flat unit sizes, this service uses:
- Kelly Criterion for mathematical optimization
- ML Conviction score for confidence-based sizing
- Account equity for risk management

Usage:
    sizer = DynamicSizer()
    
    # Calculate position size
    size = await sizer.calculate_size(
        user_id=user_id,
        signal=signal,
        ml_probability=0.85,
        win_rate=0.55,
        avg_rr=1.5
    )
    
    # Output: Risk 3% of balance based on 85% probability
"""

import logging
from typing import Any, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

# Kelly fractions
KELLY_FRACTION = 0.25  # Use 25% of full Kelly (conservative)
KELLY_MAX_RISK = 0.05  # Max 5% of balance per trade

# ML Conviction thresholds
ML_HIGH_CONVICTION = 0.75  # 75%+ probability = higher risk
ML_MEDIUM_CONVICTION = 0.60  # 60-75% = medium risk
ML_LOW_CONVICTION = 0.50  # 50-60% = low risk

# Risk tables based on ML probability
RISK_BY_PROBABILITY = {
    (0.80, 1.00): 0.03,  # 3% risk for 80%+
    (0.70, 0.80): 0.02,  # 2% risk for 70-80%
    (0.60, 0.70): 0.015,  # 1.5% risk for 60-70%
    (0.50, 0.60): 0.01,  # 1% risk for 50-60%
    (0.00, 0.50): 0.005,  # 0.5% for under 50%
}


class DynamicSizer:
    """
    Dynamic position sizer using ML probability and Kelly Criterion.
    
    This optimizes position size based on:
    1. ML model probability (conviction)
    2. Historical win rate
    3. Average risk:reward ratio
    4. Current account balance/equity
    
    The Kelly Criterion formula:
    K% = W - (1-W)/R
    Where:
    - W = win rate (probability)
    - R = average risk:reward ratio
    
    We use fractional Kelly (25%) to reduce variance.
    """
    
    def __init__(self):
        self._redis = None
        self._redis_url = self._resolve_redis_url()
        
        if self._redis_url:
            self._init_redis()
    
    def _resolve_redis_url(self) -> Optional[str]:
        import os
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
            logger.info("[dynamic_sizing] Connected to Redis")
        except Exception as e:
            logger.debug(f"[dynamic_sizing] Redis unavailable: {e}")
            self._redis = None
    
    async def calculate_size(
        self,
        user_id: int,
        signal: Dict[str, Any],
        ml_probability: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_rr: float = 1.5,
        balance: Optional[float] = None,
        equity: Optional[float] = None
    ) -> float:
        """
        Calculate optimal position size for a signal.
        
        Args:
            user_id: User ID
            signal: Signal dict with asset, direction, entry, stop_loss
            ml_probability: ML model probability (0-1)
            win_rate: Historical win rate (0-1), uses ml_probability if not provided
            avg_rr: Average risk:reward ratio
            balance: Account balance (fetched if not provided)
            equity: Current equity including open P&L (fetched if not provided)
            
        Returns:
            Suggested position size (units)
        """
        # Get balance if not provided
        if balance is None:
            try:
                from core.paper_ledger import get_paper_ledger
                ledger = get_paper_ledger()
                balance = await ledger.get_balance(user_id)
            except Exception:
                balance = 10000.0  # Default
        
        # Use equity if provided, else balance
        account_equity = equity or balance
        
        # Use ML probability as win rate if not provided
        if win_rate is None:
            win_rate = ml_probability or 0.5
        
        # Calculate risk percentage based on probability
        risk_pct = self._get_risk_by_probability(win_rate)
        
        # Optionally apply Kelly criterion
        kelly_risk = self._calculate_kelly_risk(win_rate, avg_rr)
        if kelly_risk and kelly_risk < risk_pct:
            # Use smaller of the two
            risk_pct = min(risk_pct, kelly_risk)
        
        # Limit to max risk
        risk_pct = min(risk_pct, KELLY_MAX_RISK)
        
        # Calculate position size
        entry = float(signal.get("entry", 0))
        stop_loss = float(signal.get("stop_loss") or signal.get("stop", 0))
        
        if entry <= 0 or stop_loss <= 0:
            # Default to 1% risk
            risk_pct = 0.01
            risk_amount = account_equity * risk_pct
            unit_size = risk_amount / 0.01  # Assume 1% price move
            return unit_size
        
        # Risk per unit
        if signal.get("direction", "").lower() == "long":
            risk_per_unit = entry - stop_loss
        else:
            risk_per_unit = stop_loss - entry
        
        if risk_per_unit <= 0:
            risk_per_unit = entry * 0.01  # 1% of entry
        
        # Position size
        risk_amount = account_equity * risk_pct
        size = risk_amount / risk_per_unit
        
        logger.debug(
            f"[dynamic_sizing] User {user_id}: {signal.get('asset')} "
            f"win_rate={win_rate:.2%} risk={risk_pct:.2%} size={size:.2f}"
        )
        
        return size
    
    def _get_risk_by_probability(self, probability: float) -> float:
        """Get risk percentage based on ML probability."""
        for (low, high), risk in RISK_BY_PROBABILITY.items():
            if low <= probability < high:
                return risk
        return 0.01  # Default 1%
    
    def _calculate_kelly_risk(
        self,
        win_rate: float,
        avg_rr: float
    ) -> Optional[float]:
        """
        Calculate Kelly criterion risk percentage.
        
        Kelly % = W - (1-W)/R
        
        Returns fractional Kelly (25%) capped at max.
        """
        if win_rate <= 0 or avg_rr <= 0:
            return None
        
        # Full Kelly
        kelly_full = win_rate - ((1 - win_rate) / avg_rr)
        
        if kelly_full <= 0:
            return None
        
        # Fractional Kelly
        kelly_fraction = kelly_full * KELLY_FRACTION
        
        # Return fractional Kelly (capped)
        return min(kelly_fraction, KELLY_MAX_RISK)
    
    async def calculate_size_info(
        self,
        user_id: int,
        signal: Dict[str, Any],
        ml_probability: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_rr: float = 1.5
    ) -> Dict[str, Any]:
        """
        Get detailed size calculation info.
        
        Returns dict with all the calculations for transparency.
        """
        # Get balance
        try:
            from core.paper_ledger import get_paper_ledger
            ledger = get_paper_ledger()
            balance = await ledger.get_balance(user_id)
        except Exception:
            balance = 10000.0
        
        # Calculate
        size = await self.calculate_size(
            user_id=user_id,
            signal=signal,
            ml_probability=ml_probability,
            win_rate=win_rate,
            avg_rr=avg_rr,
            balance=balance
        )
        
        # Risk percentage
        risk_pct = self._get_risk_by_probability(ml_probability or win_rate or 0.5)
        
        # Kelly
        kelly = self._calculate_kelly_risk(
            ml_probability or win_rate or 0.5,
            avg_rr
        )
        
        # Entry value
        entry = float(signal.get("entry", 0))
        entry_value = size * entry
        
        return {
            "balance": balance,
            "size": size,
            "entry_value": entry_value,
            "entry": entry,
            "stop_loss": signal.get("stop_loss"),
            "risk_pct": risk_pct,
            "risk_amount": balance * risk_pct,
            "probability": ml_probability or win_rate,
            "kelly_risk_pct": kelly,
            "avg_rr": avg_rr,
        }
    
    def get_conviction_label(self, probability: float) -> str:
        """Get human-readable conviction label."""
        if probability >= ML_HIGH_CONVICTION:
            return "HIGH"
        elif probability >= ML_MEDIUM_CONVICTION:
            return "MEDIUM"
        elif probability >= ML_LOW_CONVICTION:
            return "LOW"
        else:
            return "SPECULATIVE"


# Global sizer instance
_dynamic_sizer: Optional[DynamicSizer] = None


def get_dynamic_sizer() -> DynamicSizer:
    """Get or create the global dynamic sizer."""
    global _dynamic_sizer
    if _dynamic_sizer is None:
        _dynamic_sizer = DynamicSizer()
    return _dynamic_sizer


# Convenience function

async def calculate_position_size(
    user_id: int,
    signal: Dict[str, Any],
    ml_probability: Optional[float] = None,
    win_rate: Optional[float] = None
) -> float:
    """Calculate optimal position size."""
    sizer = get_dynamic_sizer()
    return await sizer.calculate_size(
        user_id=user_id,
        signal=signal,
        ml_probability=ml_probability,
        win_rate=win_rate
    )
