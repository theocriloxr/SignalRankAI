from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    eligible: bool
    target_state: str
    reasons: tuple[str, ...]


_ALLOWED_TRANSITIONS = {
    "SHADOW": {"FORWARD_TEST"},
    "FORWARD_TEST": {"CANARY"},
    "CANARY": {"LIMITED_LIVE"},
}


def evaluate_profile_promotion(
    metrics: Mapping[str, Any],
    *,
    human_approved: bool = False,
    target_state: str = "CANARY",
    current_state: str | None = None,
) -> PromotionGateResult:
    reasons: list[str] = []
    samples = int(metrics.get("sample_size") or 0)
    folds = int(metrics.get("positive_wfo_folds") or 0)
    expectancy = float(metrics.get("expectancy_r") or 0)
    profit_factor = float(metrics.get("profit_factor") or 0)
    drawdown = float(metrics.get("max_drawdown_r") or 999)
    calibration = float(metrics.get("brier_score") if metrics.get("brier_score") is not None else 1.0)
    leakage_ok = bool(metrics.get("leakage_checks_passed", True))
    target = str(target_state or "").upper()
    current = str(current_state or "").upper() or None

    if samples < 100:
        reasons.append("minimum_100_out_of_sample_trades")
    if folds < 3:
        reasons.append("minimum_3_positive_walk_forward_folds")
    if expectancy <= 0:
        reasons.append("non_positive_expectancy")
    if profit_factor < 1.10:
        reasons.append("profit_factor_below_1_10")
    if drawdown > 10:
        reasons.append("drawdown_above_limit")
    if calibration > 0.25:
        reasons.append("confidence_calibration_unacceptable")
    if not leakage_ok:
        reasons.append("walk_forward_leakage_check_failed")
    if not human_approved:
        reasons.append("human_approval_required")
    if target not in {"FORWARD_TEST", "CANARY", "LIMITED_LIVE"}:
        reasons.append("unsafe_target_state")
    if current is not None and target not in _ALLOWED_TRANSITIONS.get(current, set()):
        reasons.append(f"invalid_transition:{current}->{target}")

    return PromotionGateResult(not reasons, target if not reasons else "QUARANTINED", tuple(reasons))
