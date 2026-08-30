"""Canonical partial-exit accounting for lifecycle, ledger, and notifications.

The trading plan closes 50% at TP1, 25% at TP2, and leaves 25% for TP3 by
product convention. A protected exit after TP1/TP2 therefore must not be
recorded as a full -1R stop. This module is deliberately dependency-light so
runtime outcome persistence and historical ledger reconciliation use the same
formula.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except Exception:
        return None
    return result if math.isfinite(result) else None


def parse_take_profit_levels(value: Any) -> list[float]:
    if value is None:
        return []
    payload = value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = [part.strip() for part in payload.split(",") if part.strip()]
    if isinstance(payload, Mapping):
        payload = payload.get("levels") or payload.get("targets") or payload.get("take_profit") or []
    if not isinstance(payload, Sequence) or isinstance(payload, (bytes, bytearray, str)):
        payload = [payload]
    levels: list[float] = []
    for item in payload:
        if isinstance(item, Mapping):
            item = item.get("price") or item.get("target") or item.get("value")
        parsed = _float(item)
        if parsed is not None and parsed > 0:
            levels.append(parsed)
    return levels[:3]


def _fraction(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(0.0, min(1.0, value))


def planned_exit_fractions() -> tuple[float, float, float]:
    tp1 = _fraction("SIGNAL_TP1_CLOSE_FRACTION", 0.50)
    tp2 = _fraction("SIGNAL_TP2_CLOSE_FRACTION", 0.25)
    if tp1 + tp2 > 1.0:
        scale = 1.0 / (tp1 + tp2)
        tp1 *= scale
        tp2 *= scale
    runner = max(0.0, 1.0 - tp1 - tp2)
    return tp1, tp2, runner


@dataclass(frozen=True, slots=True)
class PartialExitResult:
    highest_tp: int
    realized_r: float
    realized_percent: float
    tp_r_multiples: tuple[float, ...]
    fractions: tuple[float, float, float]
    policy_version: str = "partial-exit-weighted-v2"


def calculate_partial_exit_result(
    *,
    entry: Any,
    stop_loss: Any,
    take_profit: Any,
    direction: Any,
    highest_tp: int,
    residual_exit_r: float = 0.0,
) -> PartialExitResult | None:
    entry_f = _float(entry)
    stop_f = _float(stop_loss)
    levels = parse_take_profit_levels(take_profit)
    stage = max(0, min(2, int(highest_tp or 0)))
    if entry_f is None or stop_f is None or entry_f <= 0 or stage <= 0 or len(levels) < stage:
        return None
    risk_distance = abs(entry_f - stop_f)
    if risk_distance <= 0:
        return None

    direction_s = str(direction or "").strip().lower()
    is_short = direction_s in {"short", "sell", "bearish"}
    tp_r: list[float] = []
    tp_pct: list[float] = []
    for level in levels[:stage]:
        favorable = (entry_f - level) if is_short else (level - entry_f)
        tp_r.append(max(0.0, favorable / risk_distance))
        tp_pct.append(max(0.0, (favorable / entry_f) * 100.0))

    f1, f2, runner = planned_exit_fractions()
    closed_fractions = [f1, f2]
    realized_r = 0.0
    realized_pct = 0.0
    consumed = 0.0
    for index in range(stage):
        fraction = closed_fractions[index]
        realized_r += fraction * tp_r[index]
        realized_pct += fraction * tp_pct[index]
        consumed += fraction
    remaining = max(0.0, 1.0 - consumed)
    realized_r += remaining * float(residual_exit_r or 0.0)
    # A protected/breakeven residual contributes 0% by definition.

    return PartialExitResult(
        highest_tp=stage,
        realized_r=round(realized_r, 6),
        realized_percent=round(realized_pct, 6),
        tp_r_multiples=tuple(round(value, 6) for value in tp_r),
        fractions=(round(f1, 6), round(f2, 6), round(runner, 6)),
    )


def result_from_signal(signal: Any, highest_tp: int, *, residual_exit_r: float = 0.0) -> PartialExitResult | None:
    getter = signal.get if isinstance(signal, Mapping) else lambda key, default=None: getattr(signal, key, default)
    return calculate_partial_exit_result(
        entry=getter("entry"),
        stop_loss=getter("stop_loss"),
        take_profit=getter("take_profit", getter("tp_levels", getter("targets"))),
        direction=getter("direction"),
        highest_tp=highest_tp,
        residual_exit_r=residual_exit_r,
    )


__all__ = [
    "PartialExitResult",
    "calculate_partial_exit_result",
    "parse_take_profit_levels",
    "planned_exit_fractions",
    "result_from_signal",
]
