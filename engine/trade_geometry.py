"""Canonical trade-geometry builder and validator.

All strategy candidates pass through this module before scoring. Missing stop /
target values are never defaulted to entry/current price. Geometry is either
built from asset-aware risk data (ATR) or rejected with an explicit reason.

Rejection reasons:
  - missing_trade_geometry    (entry/stop/target unresolvable)
  - non_finite_trade_geometry (NaN / infinity)
  - zero_risk_distance        (entry == stop)
  - invalid_long_geometry     (not stop < entry < target)
  - invalid_short_geometry    (not target < entry < stop)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True, slots=True)
class GeometryResult:
    ok: bool
    reason: str | None = None
    entry: float | None = None
    stop: float | None = None
    targets: tuple[float, ...] = ()
    rr: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "entry": self.entry,
            "stop": self.stop,
            "targets": list(self.targets),
            "rr": self.rr,
        }


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _has_non_finite_raw(*values: Any) -> bool:
    """Detect NaN/infinity in raw geometry inputs before numeric filtering.

    ``all_targets``/``_as_float`` silently drop non-finite values, which would
    misclassify NaN as a missing value. Non-finite inputs must be rejected
    explicitly as ``non_finite_trade_geometry``.
    """

    def _walk(value: Any) -> bool:
        if value is None or value == "" or isinstance(value, str):
            return False
        if isinstance(value, (list, tuple)):
            return any(_walk(item) for item in value)
        if isinstance(value, dict):
            return any(_walk(item) for item in value.values())
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return not math.isfinite(number)

    return any(_walk(value) for value in values)


def _primary_target(value: Any) -> float | None:
    """Resolve the first numeric target from any common shape."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _as_float(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            if isinstance(item, dict):
                parsed = _as_float(item.get("price") or item.get("tp") or item.get("target"))
            else:
                parsed = _as_float(item)
            if parsed is not None and parsed > 0:
                return parsed
        return None
    if isinstance(value, dict):
        for key in ("tp1", "price", "tp", "target", "1", "first"):
            if key in value:
                parsed = _as_float(value[key])
                if parsed is not None and parsed > 0:
                    return parsed
        return None
    return _as_float(value)


def all_targets(value: Any) -> tuple[float, ...]:
    """Resolve an ordered tuple of all valid numeric targets."""
    if value is None:
        return ()
    if isinstance(value, (int, float)):
        parsed = _as_float(value)
        return (parsed,) if parsed is not None else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out: list[float] = []
        for item in value:
            parsed = _as_float(item.get("price") or item.get("tp") or item.get("target")) if isinstance(item, dict) else _as_float(item)
            if parsed is not None and parsed > 0:
                out.append(parsed)
        return tuple(out)
    if isinstance(value, dict):
        out = []
        for key in ("tp1", "tp2", "tp3"):
            if key in value:
                parsed = _as_float(value[key])
                if parsed is not None and parsed > 0:
                    out.append(parsed)
        if not out:
            for key in ("price", "tp", "target", "1", "first"):
                if key in value:
                    parsed = _as_float(value[key])
                    if parsed is not None and parsed > 0:
                        out.append(parsed)
        return tuple(out)
    parsed = _as_float(value)
    return (parsed,) if parsed is not None else ()


def _min_price_distance(symbol: str) -> float | None:
    """Asset-aware minimum distance (tick/pip) where supported."""
    symbol_l = str(symbol or "").upper().strip()
    tick_map = {
        "XAUUSD": 0.01,
        "XAGUSD": 0.001,
        "WTI": 0.01,
        "BRENT": 0.01,
    }
    if symbol_l in tick_map:
        return tick_map[symbol_l]
    if symbol_l.startswith("BTC") or symbol_l.endswith("USDT") or symbol_l.endswith("USDC"):
        return 0.00000001  # 1e-8 tick
    if len(symbol_l) == 6 and symbol_l.isalpha():
        return 0.00001  # standard 5-digit pip for FX
    return None


def build_trade_geometry(
    signal: dict[str, Any] | None,
    *,
    atr: float | None = None,
    default_rr: float | None = None,
) -> GeometryResult:
    """Resolve entry, stop and targets through canonical risk logic.

    If stop or targets are missing, they are constructed from ATR risk when a
    direction and entry exist. If construction is impossible, the candidate is
    rejected with an explicit reason instead of defaulting to entry.
    """
    if not isinstance(signal, dict):
        return GeometryResult(False, "missing_trade_geometry")

    entry = _as_float(signal.get("entry") or signal.get("close_price"))
    direction = str(signal.get("direction") or signal.get("side") or "long").strip().lower()
    stop = _as_float(signal.get("stop_loss") or signal.get("stop"))
    targets_raw = signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    targets = all_targets(targets_raw)

    if entry is None or entry <= 0:
        return GeometryResult(False, "missing_trade_geometry")
    if direction not in {"long", "short", "buy", "sell", "bull", "bear"}:
        return GeometryResult(False, "missing_trade_geometry")

    direction_norm = "short" if direction in {"short", "sell", "bear"} else "long"

    # Construct a missing stop from ATR when available.
    if stop is None:
        atr_value = _as_float(atr) if atr is not None else _as_float(signal.get("atr"))
        if atr_value is None or atr_value <= 0:
            return GeometryResult(False, "missing_trade_geometry")
        stop = entry - 2.0 * atr_value if direction_norm == "long" else entry + 2.0 * atr_value

    # Construct missing targets from risk distance. An explicit reward ratio
    # is required — a missing RR must not silently fabricate a universal
    # DEFAULT_RR (that would invent geometry without asset-aware risk data).
    if not targets:
        risk = abs(entry - stop)
        if risk <= 0:
            return GeometryResult(False, "zero_risk_distance")
        rr = _as_float(default_rr) if default_rr is not None else _as_float(signal.get("rr"))
        if rr is None or rr <= 0:
            return GeometryResult(False, "missing_trade_geometry")
        if direction_norm == "long":
            targets = (entry + risk * rr,)
        else:
            targets = (entry - risk * rr,)

    return validate_trade_geometry(entry, stop, targets, direction_norm)


def validate_trade_geometry(
    entry: float | None,
    stop: float | None,
    targets: Iterable[float] | None,
    direction: str | None = "long",
) -> GeometryResult:
    """Validate a fully-resolved geometry without mutating any signal."""
    # NaN/infinity must be detected before numeric filtering silently drops it.
    if _has_non_finite_raw(entry, stop, list(targets) if targets is not None else None):
        return GeometryResult(False, "non_finite_trade_geometry")
    entry_f = _as_float(entry)
    stop_f = _as_float(stop)
    target_list = [t for t in (all_targets(list(targets)) if targets is not None else ())]
    if entry_f is None or stop_f is None or not target_list:
        return GeometryResult(False, "missing_trade_geometry")
    if not (math.isfinite(entry_f) and math.isfinite(stop_f) and all(math.isfinite(t) for t in target_list)):
        return GeometryResult(False, "non_finite_trade_geometry")

    direction_norm = str(direction or "long").strip().lower()
    direction_norm = "short" if direction_norm in {"short", "sell", "bear"} else "long"

    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return GeometryResult(False, "zero_risk_distance")

    primary = target_list[0]
    if direction_norm == "long":
        if not (stop_f < entry_f < primary):
            return GeometryResult(False, "invalid_long_geometry")
    else:
        if not (primary < entry_f < stop_f):
            return GeometryResult(False, "invalid_short_geometry")

    rr = abs(primary - entry_f) / risk
    return GeometryResult(True, entry=entry_f, stop=stop_f, targets=tuple(target_list), rr=rr)


__all__ = [
    "GeometryResult",
    "all_targets",
    "build_trade_geometry",
    "validate_trade_geometry",
]
