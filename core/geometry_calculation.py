"""Canonical post-geometry trade calculation.

Single source of truth for risk/reward geometry after the final entry, stop
loss and take-profit targets are established. Direction-aware and decimal-safe.
Every subsystem (scorer, quality gate, tier gate, formatter, paper trading,
outcome engine) must consume these values instead of re-deriving R:R in its
own way, so a signal can never show a generic "R:R=3.74" that disagrees with
its displayed per-target R:R values.

Rejection reasons follow the pipeline contract:

- ``missing_trade_geometry``  (entry/stop/targets absent)
- ``non_finite_trade_geometry``
- ``zero_risk_distance``       (entry == stop)
- ``invalid_long_geometry``    (stop < entry < target violated)
- ``invalid_short_geometry``   (target < entry < stop violated)
- ``unsupported_direction``
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


def decimal_value(value: Any) -> Decimal | None:
    """Parse a finite positive Decimal from arbitrary input, else None."""
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def parse_targets(targets_raw: Any) -> tuple[Decimal, ...]:
    """Normalize a take-profit payload into an ordered tuple of positive Decimals."""
    if targets_raw is None:
        return ()
    if isinstance(targets_raw, (Decimal, int, float, str)):
        items: Iterable[Any] = [targets_raw]
    elif isinstance(targets_raw, Mapping):
        ordered: list[Any] = []
        for key in ("tp1", "tp2", "tp3", "target", "price", "value"):
            if key in targets_raw:
                ordered.append(targets_raw[key])
        items = ordered or list(targets_raw.values())
    elif isinstance(targets_raw, (list, tuple)):
        items = targets_raw
    else:
        return ()
    out: list[Decimal] = []
    for item in items:
        if isinstance(item, Mapping):
            item = item.get("price") or item.get("target") or item.get("tp") or item.get("value")
        parsed = decimal_value(item)
        if parsed is not None and parsed > 0:
            out.append(parsed)
    return tuple(out[:3])


def canonical_direction(direction: Any) -> str:
    probe = str(direction or "").strip().lower()
    if probe in ("long", "buy", "bull", "bullish", "l"):
        return "long"
    if probe in ("short", "sell", "bear", "bearish", "s"):
        return "short"
    return ""


@dataclass(frozen=True, slots=True)
class GeometryResult:
    """Direction-validated trade geometry with canonical R:R values."""

    ok: bool
    reason: str
    direction: str
    entry: Decimal | None
    stop: Decimal | None
    targets: tuple[Decimal, ...]
    risk_distance: Decimal | None
    reward_distance_tp1: Decimal | None
    reward_distance_tp2: Decimal | None
    reward_distance_tp3: Decimal | None
    rr_tp1: Decimal | None
    rr_tp2: Decimal | None
    rr_tp3: Decimal | None
    rr_selected_target: Decimal | None

    def rr_display_line(self, *, tp_last: int | None = None) -> str:
        """Human display for the R/R line: 'TP1 R:R 1:1.23 • TP3 R:R 1:2.77'."""
        rr1 = self.rr_tp1
        if rr1 is None:
            return ""
        n = int(tp_last) if tp_last is not None else max(2, len(self.targets))
        rr_last = self.rr_for_index(n - 1)
        if rr_last is None:
            return f"R/R TP1 1:{float(rr1):.2f}"
        return f"R/R: TP1 1:{float(rr1):.2f} • TP{min(3, n)} 1:{float(rr_last):.2f}"

    def rr_for_index(self, index: int) -> Decimal | None:
        try:
            return (self.rr_tp1, self.rr_tp2, self.rr_tp3)[index]
        except IndexError:
            return None


def calculate_trade_geometry(
    entry: Any,
    stop: Any,
    targets: Any,
    direction: Any,
) -> GeometryResult:
    """Compute canonical risk/reward after final entry/stop/targets are set.

    LONG requires ``stop < entry < target`` for every target.
    SHORT requires ``target < entry < stop`` for every target.
    """
    direction = canonical_direction(direction)
    if not direction:
        return _failed("unsupported_direction", direction)

    entry_d = decimal_value(entry)
    stop_d = decimal_value(stop)
    target_list = parse_targets(targets)
    if entry_d is None or stop_d is None or not target_list:
        return _failed("missing_trade_geometry", direction)
    if entry_d <= 0 or stop_d <= 0:
        return _failed("non_finite_trade_geometry", direction)
    for target in target_list:
        if target <= 0:
            return _failed("non_finite_trade_geometry", direction)

    risk_distance = abs(entry_d - stop_d)
    if risk_distance <= 0:
        return _failed("zero_risk_distance", direction)

    if direction == "long":
        if not (stop_d < entry_d):
            return _failed("invalid_long_geometry", direction)
        for target in target_list:
            if not (entry_d < target):
                return _failed("invalid_long_geometry", direction)
    else:
        if not (entry_d < stop_d):
            return _failed("invalid_short_geometry", direction)
        for target in target_list:
            if not (target < entry_d):
                return _failed("invalid_short_geometry", direction)

    rewards: list[Decimal] = []
    rrs: list[Decimal] = []
    for target in target_list:
        reward = abs(target - entry_d)
        rewards.append(reward)
        rrs.append(reward / risk_distance)

    rr1 = rrs[0] if len(rrs) >= 1 else None
    rr2 = rrs[1] if len(rrs) >= 2 else None
    rr3 = rrs[2] if len(rrs) >= 3 else None
    reward1 = rewards[0] if len(rewards) >= 1 else None
    reward2 = rewards[1] if len(rewards) >= 2 else None
    reward3 = rewards[2] if len(rewards) >= 3 else None
    # Canonical selected target: the furthest valid target in the trade
    # direction (best reward), mirroring the engine's best-target convention.
    selected_rr = rrs[-1]
    return GeometryResult(
        ok=True,
        reason="",
        direction=direction,
        entry=entry_d,
        stop=stop_d,
        targets=target_list,
        risk_distance=risk_distance,
        reward_distance_tp1=reward1,
        reward_distance_tp2=reward2,
        reward_distance_tp3=reward3,
        rr_tp1=rr1,
        rr_tp2=rr2,
        rr_tp3=rr3,
        rr_selected_target=selected_rr,
    )


def _failed(reason: str, direction: str) -> GeometryResult:
    return GeometryResult(
        ok=False,
        reason=reason,
        direction=direction,
        entry=None,
        stop=None,
        targets=(),
        risk_distance=None,
        reward_distance_tp1=None,
        reward_distance_tp2=None,
        reward_distance_tp3=None,
        rr_tp1=None,
        rr_tp2=None,
        rr_tp3=None,
        rr_selected_target=None,
    )


def geometry_from_signal(signal: Mapping[str, Any]) -> GeometryResult:
    """Compute canonical geometry from a signal-style mapping."""
    return calculate_trade_geometry(
        signal.get("entry"),
        signal.get("stop_loss") if signal.get("stop_loss") not in (None, 0) else signal.get("stop"),
        signal.get("take_profit") if signal.get("take_profit") not in (None, []) else signal.get("tp_levels"),
        signal.get("direction"),
    )


def enrich_signal_geometry(signal: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *signal* with canonical geometry fields attached.

    The canonical fields (risk_distance, reward_distance_tp*, rr_tp*,
    rr_selected_target, geometry_reason) are persisted with the signal so the
    scorer, quality gate, tier gate, formatter and paper engine all read the
    same values.
    """
    out = dict(signal or {})
    result = geometry_from_signal(out)
    out["geometry_reason"] = result.reason
    if not result.ok:
        return out
    out["risk_distance"] = result.risk_distance
    out["reward_distance_tp1"] = result.reward_distance_tp1
    out["reward_distance_tp2"] = result.reward_distance_tp2
    out["reward_distance_tp3"] = result.reward_distance_tp3
    out["rr_tp1"] = result.rr_tp1
    out["rr_tp2"] = result.rr_tp2
    out["rr_tp3"] = result.rr_tp3
    out["rr_selected_target"] = result.rr_selected_target
    out["rr_ratio"] = result.rr_tp1
    if result.rr_tp3 is not None:
        out["rr_ratio"] = result.rr_tp3
    return out


__all__ = [
    "GeometryResult",
    "calculate_trade_geometry",
    "canonical_direction",
    "decimal_value",
    "enrich_signal_geometry",
    "geometry_from_signal",
    "parse_targets",
]
