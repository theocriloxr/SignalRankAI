from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
import math


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    eligible: bool
    target_state: str
    reasons: tuple[str, ...]
    policy_version: str = "research-promotion-v2"


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Versioned operator policy, never supplied by a promotion API client."""
    version: str = "research-promotion-v2"
    minimum_samples: int = 100
    minimum_positive_folds: int = 3
    minimum_positive_ratio: float = 0.6
    minimum_worst_fold_expectancy: float = -0.10
    minimum_profit_factor: float = 1.10
    maximum_drawdown_r: float = 10.0
    maximum_brier: float = 0.25

    def __post_init__(self) -> None:
        if not self.version.strip() or any(isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (self.minimum_samples, self.minimum_positive_folds)):
            raise ValueError("invalid_promotion_policy")
        values = (self.minimum_positive_ratio, self.minimum_worst_fold_expectancy,
                  self.minimum_profit_factor, self.maximum_drawdown_r, self.maximum_brier)
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValueError("invalid_promotion_policy")
        if not 0 < self.minimum_positive_ratio <= 1 or not 0 <= self.maximum_brier <= 1:
            raise ValueError("invalid_promotion_policy")
        if self.minimum_profit_factor < 1 or self.maximum_drawdown_r < 0:
            raise ValueError("invalid_promotion_policy")


DEFAULT_PROMOTION_POLICY = PromotionPolicy()


_ALLOWED_TRANSITIONS = {
    "RESEARCH": {"SHADOW"},
    "SHADOW": {"FORWARD_TEST", "PAPER"},
    "FORWARD_TEST": {"PAPER", "CANARY"},
    "PAPER": {"CANARY", "LIMITED_LIVE"},
    "CANARY": {"LIMITED_LIVE"},
    "LIMITED_LIVE": {"NORMAL_PRODUCTION"},
}


def evaluate_profile_promotion(
    metrics: Mapping[str, Any],
    *,
    human_approved: bool = False,
    target_state: str = "CANARY",
    current_state: str | None = None,
    policy: PromotionPolicy = DEFAULT_PROMOTION_POLICY,
) -> PromotionGateResult:
    reasons: list[str] = []
    def number(key: str, fallback: float) -> float:
        try:
            value = metrics[key]
            if isinstance(value, bool):
                raise ValueError("boolean_metric")
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("non_finite_metric")
            return parsed
        except (KeyError, ValueError, TypeError, OverflowError):
            reasons.append(f"missing_or_invalid_metric:{key}")
            return fallback
    samples = number("sample_size", 0)
    folds = number("positive_wfo_folds", 0)
    total_folds = number("fold_count", 0)
    expectancy = number("expectancy_r", 0)
    profit_factor = number("profit_factor", 0)
    drawdown = number("max_drawdown_r", 999)
    calibration = number("brier_score", 1)
    leakage_ok = metrics.get("leakage_checks_passed") is True
    target = str(target_state or "").upper()
    current = str(current_state or "").upper() or None

    if any(value < 0 or not float(value).is_integer() for value in (samples, folds, total_folds)):
        reasons.append("invalid_discrete_sample_or_fold_count")
    if samples < policy.minimum_samples:
        reasons.append(f"minimum_{policy.minimum_samples}_out_of_sample_trades")
    if folds < policy.minimum_positive_folds:
        reasons.append(f"minimum_{policy.minimum_positive_folds}_positive_walk_forward_folds")
    if total_folds < folds or total_folds <= 0 or folds / max(total_folds, 1) < policy.minimum_positive_ratio:
        reasons.append("walk_forward_positive_ratio_below_policy")
    if number("worst_fold_expectancy", -999) < policy.minimum_worst_fold_expectancy:
        reasons.append("worst_fold_expectancy_below_policy")
    if expectancy <= 0:
        reasons.append("non_positive_expectancy")
    if profit_factor < policy.minimum_profit_factor:
        reasons.append("profit_factor_below_1_10")
    if drawdown < 0 or drawdown > policy.maximum_drawdown_r:
        reasons.append("drawdown_above_limit")
    if calibration < 0 or calibration > policy.maximum_brier:
        reasons.append("confidence_calibration_unacceptable")
    if not leakage_ok:
        reasons.append("walk_forward_leakage_check_failed")
    for check in ("integrity_audit_passed", "trial_history_verified", "selection_bias_passed",
                  "execution_stress_passed", "risk_survival_passed", "portfolio_validation_passed",
                  "kill_conditions_approved"):
        if metrics.get(check) is not True:
            reasons.append(f"research_evidence_missing:{check}")
    if not human_approved:
        reasons.append("human_approval_required")
    if target not in {"SHADOW", "FORWARD_TEST", "PAPER", "CANARY", "LIMITED_LIVE", "NORMAL_PRODUCTION"}:
        reasons.append("unsafe_target_state")
    if current is None:
        reasons.append("current_lifecycle_state_required")
    elif target not in _ALLOWED_TRANSITIONS.get(current, set()):
        reasons.append(f"invalid_transition:{current}->{target}")

    return PromotionGateResult(not reasons, target if not reasons else "QUARANTINED", tuple(reasons), policy.version)
