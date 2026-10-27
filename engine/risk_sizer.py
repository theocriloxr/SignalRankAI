"""Bounded legacy spot sizing; qualified model weights may only reduce risk."""
from typing import Any

from engine.risk_advice import bounded_risk_percent, bounded_spot_units, finite_number
from engine.signal_metrics import resolve_calibrated_probability


class SmartRiskSizer:
    """Compatibility threshold adviser, separate from Kelly and broker sizing."""

    def __init__(self, account_balance: float = 10000.0, base_risk_pct: float = 0.01,
                 high_confidence_threshold: float = 0.85, medium_confidence_threshold: float = 0.75,
                 high_risk_multiplier: float = 1.5, medium_risk_multiplier: float = 1.0,
                 low_risk_multiplier: float = 0.5):
        self.account_balance = account_balance
        self.base_risk_pct = base_risk_pct  # Decimal fraction: 0.01 = 1%.
        self.high_confidence_threshold = high_confidence_threshold
        self.medium_confidence_threshold = medium_confidence_threshold
        self.high_risk_multiplier = high_risk_multiplier
        self.medium_risk_multiplier = medium_risk_multiplier
        self.low_risk_multiplier = low_risk_multiplier

    def get_risk_multiplier(self, ml_prob: float | None = None, *, signal: dict[str, Any] | None = None) -> float:
        """A bare probability cannot establish qualification or increase capital."""
        high, medium = finite_number(self.high_confidence_threshold), finite_number(self.medium_confidence_threshold)
        weights = [finite_number(value) for value in (self.high_risk_multiplier, self.medium_risk_multiplier, self.low_risk_multiplier)]
        if high is None or medium is None or not 0 <= medium <= high <= 1 or any(value is None or value < 0 for value in weights):
            return 0.0
        probability = resolve_calibrated_probability(signal or {})
        if probability is None:
            return 0.0 if signal is not None and signal.get("ml_calibration_validated") is True else 1.0
        selected = weights[0] if probability >= high else weights[1] if probability >= medium else weights[2]
        assert selected is not None
        return min(1.0, selected)

    def calculate_position_size(self, entry_price: float, stop_loss: float,
                                ml_probability: float | None = None, signal: dict[str, Any] | None = None,
                                *, account_state: Any = None, ml_prob: float | None = None) -> float:
        """Return conservative spot units; raw probability arguments are unqualified."""
        base, equity = finite_number(self.base_risk_pct), finite_number(self.account_balance)
        if base is None or equity is None or not 0 <= base <= 0.0125 or equity <= 0:
            return 0.0
        advice = signal or {}
        percentage = bounded_risk_percent(advice, base=base * 100,
            probability_base=1.0, probability_range=0.0, account_state=account_state)
        percentage *= self.get_risk_multiplier(ml_probability, signal=signal)
        return bounded_spot_units(equity=equity, entry=entry_price, stop=stop_loss,
            risk_amount=equity * (percentage / 100), notional_budget=equity * 0.1,
            direction=advice.get("direction"))

    def calculate_position_value(self, entry_price: float, stop_loss: float,
                                 ml_probability: float | None = None, signal: dict[str, Any] | None = None) -> float:
        price = finite_number(entry_price)
        return self.calculate_position_size(entry_price, stop_loss, ml_probability, signal) * price if price is not None else 0.0

    def get_risk_config(self) -> dict[str, Any]:
        base = finite_number(self.base_risk_pct)
        equity = finite_number(self.account_balance)
        high, medium = finite_number(self.high_confidence_threshold), finite_number(self.medium_confidence_threshold)
        weights = [finite_number(value) for value in (self.high_risk_multiplier, self.medium_risk_multiplier, self.low_risk_multiplier)]
        valid = bool(base is not None and 0 <= base <= 0.0125 and equity is not None and equity > 0
                     and high is not None and medium is not None and 0 <= medium <= high <= 1
                     and all(value is not None and value >= 0 for value in weights))
        effective = [min(1.0, value) if valid and value is not None else 0.0 for value in weights]
        valid_base = base if valid and base is not None else 0.0
        return {"account_balance": equity, "base_risk_pct": base,
            "high_confidence_threshold": high, "medium_confidence_threshold": medium,
            "high_risk_multiplier": effective[0], "medium_risk_multiplier": effective[1], "low_risk_multiplier": effective[2],
            "high_risk_pct": valid_base * effective[0], "medium_risk_pct": valid_base * effective[1], "low_risk_pct": valid_base * effective[2],
            "configuration_valid": valid, "broker_contract_certified": False, "sizing_method": "bounded_qualified_thresholds"}

    def update_account_balance(self, new_balance: float) -> None:
        self.account_balance = finite_number(new_balance) or 0.0


def get_risk_sizer(account_balance: float = 10000.0, base_risk_pct: float = 0.01) -> SmartRiskSizer:
    """Return isolated account advice; never share mutable equity across callers."""
    return SmartRiskSizer(account_balance=account_balance, base_risk_pct=base_risk_pct)


def calculate_position_size(entry_price: float, stop_loss: float, ml_probability: float | None = None,
                            account_balance: float = 10000.0, base_risk_pct: float = 0.01) -> float:
    return get_risk_sizer(account_balance, base_risk_pct).calculate_position_size(entry_price, stop_loss, ml_probability)
