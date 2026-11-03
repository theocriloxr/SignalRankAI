"""Deterministic signal quality gate shared by delivery and execution paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from core.production_integrity import calibration_evidence_valid, canonical_direction, signal_thesis_fingerprint


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _env_float(name: str, default: float) -> float:
    return _float(os.getenv(name), default)


def _targets(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, str):
        import json

        try:
            value = json.loads(value)
        except Exception:
            value = [value]
    if not isinstance(value, (list, tuple)):
        value = [value]
    out: list[float] = []
    for item in value:
        if isinstance(item, Mapping):
            item = item.get("price") or item.get("target") or item.get("tp")
        number = _float(item)
        if number > 0:
            out.append(number)
    return out


def score_floor_advisory() -> bool:
    """Owner decision (3 Nov 2026): quality-score floors record but do not veto.

    On production the score carried no information about reaching TP1 (AUC
    0.489 over 6,190 tracked candidates; docs/release/evidence/
    continuation-20261102/score_floor_test.json), so the setup-evidence filter
    decides. Only while that filter is on; QUALITY_SCORE_GATE_MODE=enforce
    restores the veto. Live execution always keeps the floor.
    """
    if str(os.getenv("QUALITY_SCORE_GATE_MODE", "advisory")).strip().lower() == "enforce":
        return False
    return str(os.getenv("SEGMENT_QUARANTINE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def meets_tier_score(score: Any, minimum: Any) -> bool:
    """Tier minimum score for delivery; a floor that only records while score_floor_advisory().

    Signals that pass this way below the minimum are delivered marked PAPER
    ONLY and are refused for live execution (evaluate_signal_quality).
    """
    return _float(score) >= _float(minimum) or score_floor_advisory()


@dataclass(frozen=True, slots=True)
class SignalQualityDecision:
    ok: bool
    reasons: tuple[str, ...]
    tp1_rr: float
    final_rr: float
    thesis_fingerprint: str
    version: str = "production-integrity-v1"


def evaluate_signal_quality(signal: Mapping[str, Any], *, execution: bool = False) -> SignalQualityDecision:
    reasons: list[str] = []
    entry = _float(signal.get("entry") or signal.get("close_price"))
    stop = _float(signal.get("stop_loss") or signal.get("stop"))
    targets = _targets(signal.get("take_profit") or signal.get("tp_levels") or signal.get("targets"))
    direction = canonical_direction(signal.get("direction"))
    risk = abs(entry - stop)
    if not str(signal.get("asset") or signal.get("symbol") or "").strip():
        reasons.append("asset_missing")
    if direction not in {"long", "short"}:
        reasons.append("direction_invalid")
    if entry <= 0 or stop <= 0 or risk <= 0:
        reasons.append("entry_stop_invalid")
    if not targets:
        reasons.append("targets_missing")

    valid_targets: list[float] = []
    if entry > 0 and stop > 0 and targets:
        if direction == "long":
            if stop >= entry:
                reasons.append("long_stop_not_below_entry")
            valid_targets = [tp for tp in targets if tp > entry]
        elif direction == "short":
            if stop <= entry:
                reasons.append("short_stop_not_above_entry")
            valid_targets = [tp for tp in targets if tp < entry]
        if len(valid_targets) != len(targets):
            reasons.append("target_geometry_invalid")

    tp1_rr = abs(valid_targets[0] - entry) / risk if valid_targets and risk > 0 else 0.0
    final_rr = abs(valid_targets[-1] - entry) / risk if valid_targets and risk > 0 else 0.0
    if tp1_rr < _env_float("QUALITY_GATE_MIN_TP1_RR", 1.0):
        reasons.append("tp1_rr_below_minimum")
    if final_rr < _env_float("QUALITY_GATE_MIN_FINAL_RR", 2.0):
        reasons.append("final_rr_below_minimum")

    score = _float(signal.get("score_calibrated") or signal.get("score_final") or signal.get("score"))
    if score < _env_float("QUALITY_GATE_MIN_SCORE", 75.0) and (execution or not score_floor_advisory()):
        reasons.append("quality_score_below_minimum")
    strategy = str(signal.get("strategy_name") or signal.get("strategy") or "").strip().lower()
    if strategy in {"", "unknown", "none", "generic"}:
        reasons.append("strategy_evidence_missing")

    # When confluence evidence is supplied, require more than a single vote.
    votes = int(_float(signal.get("confluence_vote_count") or signal.get("confluence_votes")))
    total = int(_float(signal.get("confluence_total")))
    if total > 0 and votes < int(_env_float("QUALITY_GATE_MIN_CONFLUENCE_VOTES", 2)):
        reasons.append("confluence_below_minimum")

    if execution:
        calibrated = signal.get("ml_probability_calibrated")
        calibration_version = str(signal.get("ml_calibration_version") or "").strip()
        if str(os.getenv("LIVE_EXECUTION_REQUIRES_CALIBRATED_ML", "1")).lower() in {"1", "true", "yes", "on"}:
            if calibrated is None or not calibration_version:
                reasons.append("calibrated_ml_required_for_execution")
            if not bool(signal.get("ml_calibration_validated", False)):
                reasons.append("ml_calibration_not_validated")
            minimum_rows = int(_env_float("LIVE_MIN_CALIBRATION_VALIDATION_ROWS", 100))
            if int(_float(signal.get("ml_calibration_validation_rows"))) < minimum_rows:
                reasons.append("ml_calibration_sample_too_small")
            if not calibration_evidence_valid(signal):
                reasons.append("ml_calibration_metrics_failed")
        if not bool(signal.get("quality_gate_passed", False)):
            reasons.append("persisted_quality_gate_not_passed")
        if signal.get("score_floor_advisory"):
            reasons.append("score_floor_advisory_paper_only")

    return SignalQualityDecision(
        ok=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        tp1_rr=float(tp1_rr),
        final_rr=float(final_rr),
        thesis_fingerprint=signal_thesis_fingerprint(signal),
    )


__all__ = ["SignalQualityDecision", "evaluate_signal_quality", "meets_tier_score", "score_floor_advisory"]
