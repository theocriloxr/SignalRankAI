"""
Spot-unit sizing advice using supplied historical estimates.

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

Raw model confidence is never substituted for an empirical win-rate estimate.
This helper does not verify that estimate or size broker lots/contracts. Venue
specifications and account/portfolio risk limits remain authoritative.
"""

import logging
import math
from typing import Any, Dict, Optional

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
        # Sizing is pure and must not perform import-time network I/O.
        self._redis = None

    async def calculate_size(
        self,
        user_id: int,
        signal: Dict[str, Any],
        ml_probability: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_rr: float = 1.5,
        balance: Optional[float] = None,
        equity: Optional[float] = None,
    ) -> float:
        """
        Calculate optimal position size for a signal.

        Args:
            user_id: User ID
            signal: Signal dict with asset, direction, entry, stop_loss
            ml_probability: ML model probability (0-1)
            win_rate: Supplied historical win rate (0-1); required independently of ML
            avg_rr: Average risk:reward ratio
            balance: Account balance (fetched if not provided)
            equity: Current equity including open P&L (fetched if not provided)

        Returns:
            Suggested position size (units)
        """
        # A raw forecast cannot establish empirical edge or authorize risk.
        if win_rate is None or isinstance(win_rate, bool) or isinstance(avg_rr, bool):
            return 0.0
        # Get balance if not provided
        if balance is None:
            try:
                from core.paper_ledger import get_paper_ledger

                ledger = get_paper_ledger()
                balance = await ledger.get_balance(user_id)
            except Exception:
                balance = None

        # Unknown account equity blocks a size recommendation; never invent a
        # $10,000 balance. Zero equity also remains zero instead of falling
        # back to another value.
        account_equity = equity if equity is not None else balance
        if account_equity is None or isinstance(account_equity, bool):
            return 0.0
        try:
            account_equity = float(account_equity)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(account_equity) or account_equity <= 0:
            return 0.0

        # Missing probability is not evidence. Use no allocation rather than
        # manufacturing a 50% forecast.
        try:
            win_rate = float(win_rate)
            avg_rr = float(avg_rr)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(win_rate) or not math.isfinite(avg_rr) or not 0.0 <= win_rate <= 1.0 or avg_rr <= 0:
            return 0.0

        # Calculate risk percentage based on probability
        risk_pct = self._get_risk_by_probability(win_rate)

        # Optionally apply Kelly criterion
        kelly_risk = self._calculate_kelly_risk(win_rate, avg_rr)
        if kelly_risk is None or kelly_risk <= 0:
            return 0.0
        risk_pct = min(risk_pct, kelly_risk)

        # Limit to max risk
        risk_pct = min(risk_pct, KELLY_MAX_RISK)

        # Calculate position size
        try:
            if isinstance(signal.get("entry"), bool) or isinstance(signal.get("stop_loss") or signal.get("stop"), bool):
                return 0.0
            entry = float(signal.get("entry", 0))
            stop_loss = float(signal.get("stop_loss") or signal.get("stop", 0))
        except (TypeError, ValueError, OverflowError):
            return 0.0

        if not math.isfinite(entry) or not math.isfinite(stop_loss) or entry <= 0 or stop_loss <= 0:
            return 0.0

        # Risk per unit
        direction = str(signal.get("direction") or "").lower()
        if direction in {"long", "buy"}:
            risk_per_unit = entry - stop_loss
        elif direction in {"short", "sell"}:
            risk_per_unit = stop_loss - entry
        else:
            return 0.0
        if risk_per_unit <= 0:
            return 0.0

        # Position size
        risk_amount = account_equity * risk_pct
        size = risk_amount / risk_per_unit

        logger.debug(
            f"[dynamic_sizing] User {user_id}: {signal.get('asset')} "
            f"win_rate={win_rate:.2%} risk={risk_pct:.2%} size={size:.2f}"
        )

        return size if math.isfinite(size) and size > 0 else 0.0

    def _get_risk_by_probability(self, probability: float) -> float:
        """Get risk percentage based on ML probability."""
        if probability == 1.0:
            return RISK_BY_PROBABILITY[(0.80, 1.00)]
        for (low, high), risk in RISK_BY_PROBABILITY.items():
            if low <= probability < high:
                return risk
        return 0.0

    def _calculate_kelly_risk(self, win_rate: float, avg_rr: float) -> Optional[float]:
        """
        Calculate Kelly criterion risk percentage.

        Kelly % = W - (1-W)/R

        Returns fractional Kelly (25%) capped at max.
        """
        if not math.isfinite(win_rate) or not math.isfinite(avg_rr) or not 0 <= win_rate <= 1 or avg_rr <= 0:
            return None

        # Full Kelly
        # The equivalent payoff form avoids a spurious positive allocation at
        # common exact break-even inputs such as p=0.4, R=1.5.
        kelly_full = (win_rate * (avg_rr + 1) - 1) / avg_rr

        if kelly_full <= 0:
            return 0.0

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
        avg_rr: float = 1.5,
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
            balance = None

        # Calculate
        size = await self.calculate_size(
            user_id=user_id,
            signal=signal,
            ml_probability=ml_probability,
            win_rate=win_rate,
            avg_rr=avg_rr,
            balance=balance,
        )

        probability = win_rate
        try:
            kelly = self._calculate_kelly_risk(float(win_rate), float(avg_rr)) if win_rate is not None else None
            entry = float(signal.get("entry", 0))
            stop = float(signal.get("stop_loss") or signal.get("stop", 0))
            risk_amount = size * abs(entry - stop) if size > 0 else 0.0
            risk_pct = risk_amount / float(balance) if size > 0 and balance is not None else 0.0
        except (TypeError, ValueError, OverflowError):
            entry, risk_amount, risk_pct, kelly = None, 0.0, 0.0, None

        # Entry value
        entry_value = size * entry if entry is not None and math.isfinite(entry) else 0.0

        return {
            "balance": balance,
            "size": size,
            "entry_value": entry_value,
            "entry": entry,
            "stop_loss": signal.get("stop_loss"),
            "risk_pct": risk_pct,
            "risk_amount": risk_amount,
            "probability": probability,
            "probability_source": "supplied_historical_win_rate_unverified",
            "ml_probability": ml_probability,
            "instrument_sizing_certified": False,
            "sizing_status": "ok" if size > 0 else "blocked_missing_or_invalid_inputs",
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
    user_id: int, signal: Dict[str, Any], ml_probability: Optional[float] = None, win_rate: Optional[float] = None
) -> float:
    """Calculate optimal position size."""
    sizer = get_dynamic_sizer()
    return await sizer.calculate_size(user_id=user_id, signal=signal, ml_probability=ml_probability, win_rate=win_rate)
