"""Canonical risk presets for connected trading accounts.

Percentages are decimal fractions. Presets are starting points, never a promise
of performance. Account/prop-firm rules may only make these limits stricter.
"""
from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

_CONSERVATIVE = MappingProxyType({
    "max_risk_per_trade_pct": Decimal("0.005"),   # 0.50%
    "max_daily_loss_pct": Decimal("0.02"),        # 2.00%
    "max_weekly_loss_pct": Decimal("0.04"),       # 4.00%
    "max_total_drawdown_pct": Decimal("0.06"),    # 6.00%
    "max_open_positions": 3,
    "max_spread_bps": Decimal("50"),
    "max_slippage_bps": Decimal("25"),
})

_LIVE_CANARY = MappingProxyType({
    "max_risk_per_trade_pct": Decimal("0.0025"),  # 0.25%
    "max_daily_loss_pct": Decimal("0.01"),        # 1.00%
    "max_weekly_loss_pct": Decimal("0.02"),       # 2.00%
    "max_total_drawdown_pct": Decimal("0.03"),    # 3.00%
    "max_open_positions": 1,
    "max_spread_bps": Decimal("35"),
    "max_slippage_bps": Decimal("15"),
})

_PAPER_DEMO = MappingProxyType({
    "max_risk_per_trade_pct": Decimal("0.005"),
    "max_daily_loss_pct": Decimal("0.02"),
    "max_weekly_loss_pct": Decimal("0.04"),
    "max_total_drawdown_pct": Decimal("0.06"),
    "max_open_positions": 3,
    "max_spread_bps": Decimal("75"),
    "max_slippage_bps": Decimal("40"),
})

RISK_PRESETS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    "paper_demo": _PAPER_DEMO,
    "conservative": _CONSERVATIVE,
    "live_canary": _LIVE_CANARY,
})

def get_risk_preset(name: str = "conservative") -> dict[str, Any]:
    key=str(name or "conservative").strip().lower()
    if key not in RISK_PRESETS:
        raise ValueError("unknown_risk_preset")
    return dict(RISK_PRESETS[key])

def apply_external_caps(
    policy: Mapping[str, Any],
    *,
    external_daily: Decimal | None = None,
    external_weekly: Decimal | None = None,
    external_total: Decimal | None = None,
    safety_buffer_pct: Decimal = Decimal("0"),
) -> dict[str, Any]:
    """Return a copy whose loss caps are never looser than external rules."""
    out=dict(policy)
    buffer=max(Decimal("0"), min(Decimal("0.50"), Decimal(str(safety_buffer_pct))))
    for key, external in (
        ("max_daily_loss_pct", external_daily),
        ("max_weekly_loss_pct", external_weekly),
        ("max_total_drawdown_pct", external_total),
    ):
        if external is None:
            continue
        ext=max(Decimal("0"), Decimal(str(external)) - buffer)
        current=Decimal(str(out.get(key, ext)))
        out[key]=min(current, ext)
    return out

__all__=["RISK_PRESETS","get_risk_preset","apply_external_caps"]
