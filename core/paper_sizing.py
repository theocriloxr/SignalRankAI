"""Decimal-only, fee-aware paper position sizing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any


MONEY_QUANTUM = Decimal("0.00000001")
QUANTITY_QUANTUM = Decimal("0.000000000001")
SIZING_POLICY_VERSION = "paper-fee-reserve-v2"


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        parsed = Decimal(default)
    return parsed if parsed.is_finite() else Decimal(default)


@dataclass(frozen=True, slots=True)
class PaperPositionSize:
    """Fee-aware paper size plus the requested-vs-actual risk separation.

    ``risk_amount`` is the *requested* risk budget (cash x risk_pct). The actual
    stop risk is ``risk_per_unit x executed quantity`` and is reported separately
    (``actual_risk_amount`` / ``actual_risk_pct``) so a cash/notional cap never
    masquerades as the planned 1% risk.
    """

    quantity: Decimal
    notional: Decimal
    entry_fee: Decimal
    total_required: Decimal
    risk_amount: Decimal
    configured_notional_cap: Decimal
    fee_adjusted_cash_cap: Decimal
    affordable_notional: Decimal
    # Requested vs actual risk separation (Phase 4)
    requested_risk_pct: Decimal
    risk_per_unit: Decimal
    uncapped_quantity: Decimal
    actual_risk_amount: Decimal
    actual_risk_pct: Decimal
    size_cap_applied: bool
    size_cap_reason: str
    available_cash_before: Decimal
    available_cash_after: Decimal
    policy_version: str = SIZING_POLICY_VERSION

    @property
    def executed_quantity(self) -> Decimal:
        return self.quantity

    @property
    def executed_notional(self) -> Decimal:
        return self.notional

    @property
    def margin_required(self) -> Decimal:
        return self.notional

    @property
    def fees(self) -> Decimal:
        return self.entry_fee


def calculate_paper_position_size(
    *,
    cash: Any,
    risk_pct: Any,
    risk_per_unit: Any,
    fill: Any,
    max_notional_pct: Any,
    fee_bps: Any,
    tolerance: Any = "0.00000001",
) -> PaperPositionSize:
    cash_d = decimal_value(cash)
    risk_pct_d = decimal_value(risk_pct)
    risk_unit_d = decimal_value(risk_per_unit)
    fill_d = decimal_value(fill)
    cap_pct_d = decimal_value(max_notional_pct)
    fee_rate = decimal_value(fee_bps) / Decimal("10000")
    tolerance_d = abs(decimal_value(tolerance, "0.00000001"))
    if cash_d <= 0:
        raise ValueError("cash_must_be_positive")
    if risk_pct_d <= 0:
        raise ValueError("risk_pct_must_be_positive")
    if risk_unit_d <= tolerance_d:
        raise ValueError("invalid_risk_distance")
    if fill_d <= 0:
        raise ValueError("fill_must_be_positive")
    if not (Decimal("0") < cap_pct_d <= Decimal("100")):
        raise ValueError("max_notional_pct_out_of_range")
    if fee_rate < 0:
        raise ValueError("fee_rate_must_not_be_negative")

    configured_cap = cash_d * cap_pct_d / Decimal("100")
    fee_adjusted_cap = cash_d / (Decimal("1") + fee_rate)
    affordable = min(configured_cap, fee_adjusted_cap)
    risk_amount = cash_d * risk_pct_d / Decimal("100")
    risk_quantity = risk_amount / risk_unit_d
    cash_quantity = affordable / fill_d
    quantity = min(risk_quantity, cash_quantity).quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN)
    notional = (quantity * fill_d).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
    entry_fee = (notional * fee_rate).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
    required = notional + entry_fee
    if quantity <= 0 or required > cash_d + tolerance_d:
        raise ValueError("insufficient_virtual_cash")
    # Phase 4: separate requested risk from actual stop risk.
    actual_risk_amount = (risk_unit_d * quantity).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
    equity_before = cash_d
    actual_risk_pct = (
        (actual_risk_amount / equity_before * Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
        if equity_before > 0
        else Decimal("0")
    )
    capped = quantity < risk_quantity - tolerance_d
    if capped:
        cap_reason = "available_virtual_cash" if quantity < cash_quantity - tolerance_d else "configured_notional_cap"
    else:
        cap_reason = "none"
    return PaperPositionSize(
        quantity=quantity,
        notional=notional,
        entry_fee=entry_fee,
        total_required=required,
        risk_amount=risk_amount,
        configured_notional_cap=configured_cap,
        fee_adjusted_cash_cap=fee_adjusted_cap,
        affordable_notional=affordable,
        requested_risk_pct=risk_pct_d,
        risk_per_unit=risk_unit_d,
        uncapped_quantity=risk_quantity,
        actual_risk_amount=actual_risk_amount,
        actual_risk_pct=actual_risk_pct,
        size_cap_applied=capped,
        size_cap_reason=cap_reason,
        available_cash_before=cash_d,
        available_cash_after=(cash_d - required).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN),
    )


def paper_risk_report_text(sizing: PaperPositionSize) -> str:
    """Three-line requested-vs-actual risk report for paper notifications."""
    requested_pct = float(sizing.requested_risk_pct)
    actual_amt = float(sizing.actual_risk_amount)
    actual_pct = float(sizing.actual_risk_pct)
    cap_text = "none" if not sizing.size_cap_applied else sizing.size_cap_reason.replace("_", " ")
    return (
        f"Requested risk budget: {requested_pct:.2f}%\n"
        f"Actual stop risk: ${actual_amt:.2f} ({actual_pct:.2f}%)\n"
        f"Position-size cap: {cap_text}"
    )


__all__ = [
    "PaperPositionSize",
    "SIZING_POLICY_VERSION",
    "calculate_paper_position_size",
    "decimal_value",
]
