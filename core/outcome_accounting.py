"""Price-backed outcome arithmetic shared by persistence and reconciliation."""

from __future__ import annotations

import math
from typing import Any

from core.partial_exit_accounting import parse_take_profit_levels


def outcome_price_metrics(signal: Any, status: str, price: float | None) -> tuple[float | None, float | None]:
    """Reject incompatible exits; never manufacture profit by taking abs(P/L)."""
    status = str(status or "").strip().lower()
    if status in {"missed", "missed_entry", "expired", "pending"}:
        return None, None
    if status not in {"tp", "tp1", "tp2", "tp3", "sl", "time_stop", "partial_win_be"}:
        raise ValueError("outcome_status_unknown")
    entry = float(getattr(signal, "entry", 0) or 0)
    stop = float(getattr(signal, "stop_loss", 0) or 0)
    mark = float(price or 0)
    side = str(getattr(signal, "direction", "") or "").strip().lower()
    if side not in {"long", "buy", "bullish", "short", "sell", "bearish"}:
        raise ValueError("outcome_direction_unknown")
    if not all(math.isfinite(value) and value > 0 for value in (entry, stop, mark)) or entry == stop:
        raise ValueError("outcome_price_or_risk_invalid")
    short = side in {"short", "sell", "bearish"}
    if (short and stop <= entry) or (not short and stop >= entry):
        raise ValueError("outcome_stop_geometry_invalid")
    signed_move = entry - mark if short else mark - entry
    if status in {"tp", "tp1", "tp2", "tp3"}:
        stage = 3 if status == "tp" else int(status[2:])
        targets = sorted(parse_take_profit_levels(getattr(signal, "take_profit", None)), reverse=short)
        if len(targets) < stage:
            raise ValueError("outcome_target_missing")
        target = targets[stage - 1]
        if (short and target >= entry) or (not short and target <= entry):
            raise ValueError("outcome_target_geometry_invalid")
        if (short and mark > target) or (not short and mark < target):
            raise ValueError("outcome_target_not_crossed")
    elif status == "sl" and ((short and mark < stop) or (not short and mark > stop)):
        raise ValueError("outcome_stop_not_crossed")
    return signed_move / abs(entry - stop), signed_move / entry * 100.0
