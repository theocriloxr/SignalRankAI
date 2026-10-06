"""Bounded spot-unit risk advice, separate from broker/account certification."""

from utils.timeutils import now_utc_naive

import os
import math
import logging
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

from engine.risk_advice import bounded_risk_percent, finite_number as _finite_number

logger = logging.getLogger(__name__)

# Realtime dynamic config (no fixed values beyond env defaults)
BASE_RISK_PCT = _finite_number(os.getenv("RISK_PER_TRADE_PCT", "0.5"))  # Invalid input disables risk advice.
MAX_ACTIVE_TRADES = int(os.getenv("MAX_ACTIVE_TRADES", "3"))  # Reduced for safety
TRADE_COOLDOWN_MINUTES = int(os.getenv("TRADE_COOLDOWN_MINUTES", "15"))
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "3.0"))  # Reduced
MIN_RR_RATIO = float(os.getenv("MIN_RR_RATIO", "1.5"))


class RiskManager:
    """Enhanced dynamic risk manager using realtime data sources."""

    def __init__(self, account_equity: float):
        self.account_equity = account_equity
        self.correlation_manager = CorrelationManager()

    def get_dynamic_risk_pct(self, signal: Dict, account_state: Optional[Any] = None) -> float:
        """Use the shared bounded advice policy; venue/account rules apply later."""
        return bounded_risk_percent(signal, base=BASE_RISK_PCT,
            probability_base=os.getenv("ML_RISK_BASE", "0.5"),
            probability_range=os.getenv("ML_RISK_RANGE", "0.5"), account_state=account_state)

    def calculate_position_size(self, signal: Dict, account_equity: float, **kwargs) -> float:
        """Enhanced: equity * dynamic_pct / risk_distance."""
        entry, stop, equity = (_finite_number(signal.get("entry")), _finite_number(signal.get("stop_loss")), _finite_number(account_equity))
        if entry is None or stop is None or equity is None or min(entry, stop, equity) <= 0:
            return 0.0
        direction = str(signal.get("direction") or "").lower()
        if (direction in {"long", "buy"} and stop >= entry) or (direction in {"short", "sell"} and stop <= entry) or (direction and direction not in {"long", "buy", "short", "sell"}):
            return 0.0
        risk_dist = abs(entry - stop)

        if risk_dist <= 0:
            return 0.0

        risk_pct = self.get_dynamic_risk_pct(signal, account_state=kwargs.get("account_state"))
        if risk_pct <= 0:
            return 0.0
        risk_amount = equity * (risk_pct / 100)
        size = risk_amount / risk_dist

        # Bounds + vol adjust
        # Convert the quote-currency notional cap to units. No minimum lot may
        # increase the loss budget or revive an account hard stop.
        size = min(size, equity * 0.1 / entry)
        vol_regime = signal.get("vol_regime", "medium")
        if vol_regime == "high":
            size *= 0.7

        if not math.isfinite(size) or size <= 0:
            return 0.0
        if size * risk_dist > risk_amount or size * entry > equity * 0.1:
            size = math.nextafter(size, 0.0)
        return size if size * risk_dist <= risk_amount and size * entry <= equity * 0.1 else 0.0

    # Existing methods preserved for compatibility
    def calculate_atr_stops(self, current_price: float, atr: float, direction: int = 1) -> Dict[str, float]:
        if direction == 1:  # Long
            stop_loss = current_price - (2 * atr)
            take_profit = current_price + (4 * atr)
            rr_ratio = (
                (take_profit - current_price) / (current_price - stop_loss) if (current_price - stop_loss) > 0 else 0
            )
        else:  # Short
            stop_loss = current_price + (2 * atr)
            take_profit = current_price - (4 * atr)
            rr_ratio = (
                (current_price - take_profit) / (stop_loss - current_price) if (stop_loss - current_price) > 0 else 0
            )

        return {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr_ratio": max(1.5, rr_ratio),
            "risk_distance": abs(current_price - stop_loss),
            "reward_distance": abs(take_profit - current_price),
        }

    def validate_rr_ratio(
        self, entry: float, stop_loss: float, take_profit: float, min_ratio: float = MIN_RR_RATIO
    ) -> Tuple[bool, float]:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk <= 0:
            return False, 0
        rr_ratio = reward / risk
        return rr_ratio >= min_ratio, rr_ratio

    def can_open_trade(self, active_trades: int, last_trade_time: Optional[datetime] = None) -> Tuple[bool, str]:
        if active_trades >= MAX_ACTIVE_TRADES:
            return False, f"Max active trades ({MAX_ACTIVE_TRADES}) reached"
        if last_trade_time:
            time_since_last = now_utc_naive() - last_trade_time
            if time_since_last < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                remaining = TRADE_COOLDOWN_MINUTES - int(time_since_last.total_seconds() / 60)
                return False, f"Trade cooldown: {remaining}m remaining"
        return True, "OK"

    def calculate_trailing_stop(
        self, entry_price: float, current_price: float, atr: float, direction: int = 1
    ) -> Optional[float]:
        trail_mult = float(os.getenv("TRAILING_STOP_ATR_MULT", "0.5") or 0.5)
        trail_mult = max(0.1, min(trail_mult, 2.0))
        if direction == 1:  # Long
            if current_price <= entry_price:
                return entry_price - (2 * atr)
            trailing_stop = current_price - (trail_mult * atr)
            return max(trailing_stop, entry_price - (2 * atr))
        else:  # Short
            if current_price >= entry_price:
                return entry_price + (2 * atr)
            trailing_stop = current_price + (trail_mult * atr)
            return min(trailing_stop, entry_price + (2 * atr))

    # Partial exits
    def calculate_partial_exit_levels(
        self, entry: float, take_profit: float, direction: int = 1, num_levels: int = 3
    ) -> List[Dict[str, float | str]]:
        if direction == 1:  # Long
            tp_distance = take_profit - entry
            return [
                {"price": entry + (tp_distance * i / num_levels), "quantity_pct": 100 / num_levels, "label": f"TP{i}"}
                for i in range(1, num_levels + 1)
            ]
        else:  # Short
            tp_distance = entry - take_profit
            return [
                {"price": entry - (tp_distance * i / num_levels), "quantity_pct": 100 / num_levels, "label": f"TP{i}"}
                for i in range(1, num_levels + 1)
            ]


class SmartRiskSizer:
    """
    Legacy threshold-based unit sizing; this is not Kelly sizing.

    Scales position size dynamically based on:
    1. Stop Loss Distance (ATR)
    2. ML Conviction Score

    Logic:
    - If ML Conviction >= 85%: Risk 1.5%
    - If ML Conviction >= 75%: Risk 1.0%
    - If ML Conviction < 75%: Risk 0.5%

    Formula: Risk Amount / Stop Loss Distance = Position Size
    """

    def __init__(self, account_balance: float = 10000.0, base_risk_pct: float = 0.01):
        self.account_balance = account_balance
        self.base_risk_pct = base_risk_pct  # Base risk: 1% of account

    def get_risk_multiplier(self, ml_prob: float) -> float:
        """Get risk multiplier based on ML probability."""
        if ml_prob >= 0.85:
            return 1.5  # High Conviction = Risk 1.5%
        elif ml_prob >= 0.75:
            return 1.0  # Normal Conviction = Risk 1.0%
        else:
            return 0.5  # Low Conviction = Risk 0.5%

    def calculate_position_size(self, entry_price: float, stop_loss: float, ml_prob: float) -> float:
        """
        Calculate exact unit size based on conviction and SL distance.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            ml_prob: ML probability (0-1)

        Returns:
            Position size in units
        """
        # 1. Scale risk based on ML Probability
        risk_multiplier = self.get_risk_multiplier(ml_prob)

        actual_risk_amount = self.account_balance * (self.base_risk_pct * risk_multiplier)

        # 2. Calculate distance to Stop Loss (Absolute)
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance == 0:
            return 0.0

        # 3. Calculate Position Size
        # Risk Amount / Stop Loss Distance = Number of Units
        position_size = actual_risk_amount / sl_distance

        logger.info(
            f"📐 RISK SIZER: ML Prob {ml_prob * 100:.1f}% -> "
            f"Risk Multiplier {risk_multiplier}x -> "
            f"Risking ${actual_risk_amount:.2f}. Size: {position_size:.4f} units"
        )

        return position_size


class CorrelationManager:
    """Realtime correlation avoidance."""

    def __init__(self):
        self.correlation_matrix = {}

    def calculate_pair_correlation(self, returns1: np.ndarray, returns2: np.ndarray) -> float:
        if len(returns1) < 2 or len(returns2) < 2:
            return 0
        try:
            corr = np.corrcoef(returns1, returns2)[0, 1]
            return float(corr) if not np.isnan(corr) else 0
        except:
            return 0

    def can_add_correlated_position(
        self,
        new_pair: str,
        existing_pairs: List[str],
        max_correlation: float = 0.7,
        returns_data: Optional[Dict[str, np.ndarray]] = None,
    ) -> Tuple[bool, str]:
        if not existing_pairs or not returns_data:
            return True, "No correlation check needed"
        for existing in existing_pairs:
            if new_pair not in returns_data or existing not in returns_data:
                continue
            corr = self.calculate_pair_correlation(returns_data[new_pair], returns_data[existing])
            if abs(corr) > max_correlation:
                return False, f"High correlation with {existing}: {corr:.2f}"
        return True, "OK"
