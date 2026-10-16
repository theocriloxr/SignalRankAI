from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
import math
from statistics import median, pstdev
from typing import Mapping, Sequence

from .dataset import AdaptiveDatasetRow
from .availability import audit_sequence_availability
from .statistics import profit_factor as _profit_factor


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold: int
    train_count: int
    validation_count: int
    train_end: str
    validation_start: str
    validation_end: str
    baseline_expectancy_r: float
    candidate_expectancy_r: float
    candidate_profit_factor: float | None
    candidate_max_drawdown_r: float
    positive: bool
    purged_count: int = 0
    train_outcome_end: str | None = None
    profit_factor_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    fold_count: int
    positive_folds: int
    sample_size: int
    expectancy_r: float
    profit_factor: float | None
    max_drawdown_r: float
    folds: tuple[WalkForwardFold, ...]
    leakage_checks_passed: bool
    reasons: tuple[str, ...]
    positive_fold_ratio: float = 0.0
    worst_fold_expectancy: float | None = None
    worst_fold_profit_factor: float | None = None
    worst_fold_drawdown: float | None = None
    median_fold_expectancy: float | None = None
    fold_dispersion: float | None = None
    validation_returns_r: tuple[float, ...] = ()
    profit_factor_reason: str | None = None
    worst_fold_profit_factor_reason: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["folds"] = [asdict(fold) for fold in self.folds]
        payload["method_version"] = "purged_outcome_weighting_v4"
        return payload


def _max_drawdown(values: Sequence[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _training_weight(values: Sequence[float], minimum_observations: int = 10) -> float:
    if len(values) < minimum_observations:
        return 1.0
    expectancy = sum(values) / len(values)
    reliability = min(1.0, len(values) / max(minimum_observations * 3, 1))
    value = 1.0 + max(-0.15, min(0.15, expectancy * 0.08)) * reliability
    pf = _profit_factor(values)
    if pf is not None and pf < 1.0:
        value = min(value, 0.90)
    return max(0.80, min(1.15, value))


def walk_forward_evaluate(
    rows: Sequence[AdaptiveDatasetRow],
    *,
    family_weights: Mapping[str, float],
    regime_weights: Mapping[str, float] | None = None,
    minimum_train: int = 80,
    validation_size: int = 30,
    embargo_seconds: int = 0,
    cost_r: float = 0.0,
) -> WalkForwardResult:
    if minimum_train < 1 or validation_size < 1 or embargo_seconds < 0:
        raise ValueError("invalid_walk_forward_window")
    if not math.isfinite(cost_r) or cost_r < 0:
        raise ValueError("invalid_walk_forward_cost")
    ordered = sorted(rows, key=lambda item: (item.decision_time, item.signal_id))
    reasons: list[str] = []
    if len({row.signal_id for row in ordered}) != len(ordered):
        reasons.append("duplicate_signal_observations")
    if any(row.outcome_known_at is None for row in ordered):
        reasons.append("outcome_availability_unverified")
    if any(not math.isfinite(row.r_multiple) for row in ordered):
        reasons.append("non_finite_outcomes")
    if any(audit_sequence_availability(row.sequence_provenance, asset=row.asset,
            decision_time=row.decision_time, sequence_hashes=row.sequence_hashes)["status"] == "FAIL"
            for row in ordered):
        reasons.append("sequence_availability_violation")
    if len({row.evidence_category for row in ordered}) > 1:
        reasons.append("mixed_evidence_categories")
    if reasons:
        return WalkForwardResult(0, 0, 0, 0.0, None, 0.0, (), False, tuple(reasons),
                                 profit_factor_reason="no_validation_observations")
    if len(ordered) < minimum_train + validation_size:
        return WalkForwardResult(0, 0, 0, 0.0, None, 0.0, (), False, ("insufficient_chronological_rows",),
                                 profit_factor_reason="no_validation_observations")
    regime_weights = regime_weights or {}
    folds: list[WalkForwardFold] = []
    candidate_all: list[float] = []
    cursor = minimum_train
    fold_number = 1
    while cursor + validation_size <= len(ordered):
        train = ordered[:cursor]
        validation_start = ordered[cursor].decision_time
        train_cutoff = validation_start - timedelta(seconds=max(0, embargo_seconds))
        purged_train = [
            row for row in train
            if row.decision_time < train_cutoff
            and row.outcome_known_at is not None and row.outcome_known_at < train_cutoff
        ]
        validation = ordered[cursor : cursor + validation_size]
        if len(purged_train) < minimum_train:
            reasons.append(f"fold_{fold_number}_insufficient_purged_training_rows")
            cursor += validation_size
            fold_number += 1
            continue
        # Learn fold-specific weights strictly from the purged training window.
        # The supplied mappings define optional allowed families/regimes only; their
        # values are never used as future-derived validation weights.
        train_by_family: dict[str, list[float]] = {}
        train_by_regime: dict[str, list[float]] = {}
        for train_row in purged_train:
            train_by_family.setdefault(train_row.family, []).append(train_row.r_multiple)
            train_by_regime.setdefault(train_row.regime, []).append(train_row.r_multiple)
        fold_family_weights = {key: _training_weight(values) for key, values in train_by_family.items()}
        fold_regime_weights = {key: _training_weight(values) for key, values in train_by_regime.items()}

        baseline = [row.r_multiple - cost_r for row in validation]
        candidate: list[float] = []
        for row in validation:
            family_weight = fold_family_weights.get(row.family, 1.0)
            regime_weight = fold_regime_weights.get(row.regime, 1.0)
            # Weighting is treated as bounded participation/risk, not fabricated trade return.
            candidate.append((row.r_multiple * family_weight * regime_weight) - cost_r)
        baseline_exp = sum(baseline) / len(baseline)
        candidate_exp = sum(candidate) / len(candidate)
        pf = _profit_factor(candidate)
        dd = _max_drawdown(candidate)
        positive = candidate_exp > baseline_exp and candidate_exp > 0 and pf is not None and pf >= 1.0
        folds.append(
            WalkForwardFold(
                fold=fold_number,
                train_count=len(purged_train),
                validation_count=len(validation),
                train_end=purged_train[-1].decision_time.isoformat(),
                validation_start=validation[0].decision_time.isoformat(),
                validation_end=validation[-1].decision_time.isoformat(),
                baseline_expectancy_r=round(baseline_exp, 8),
                candidate_expectancy_r=round(candidate_exp, 8),
                candidate_profit_factor=round(pf, 8) if pf is not None else None,
                candidate_max_drawdown_r=round(dd, 8),
                positive=positive,
                purged_count=len(train) - len(purged_train),
                train_outcome_end=max(row.outcome_known_at for row in purged_train if row.outcome_known_at).isoformat(),
                profit_factor_reason="no_observed_losses" if pf is None else None,
            )
        )
        candidate_all.extend(candidate)
        cursor += validation_size
        fold_number += 1
    expectancy = sum(candidate_all) / len(candidate_all) if candidate_all else 0.0
    leakage_ok = bool(folds) and all("insufficient_purged_training_rows" in reason for reason in reasons)
    expectations = [fold.candidate_expectancy_r for fold in folds]
    aggregate_pf = _profit_factor(candidate_all) if candidate_all else None
    fold_factors = [fold.candidate_profit_factor for fold in folds if fold.candidate_profit_factor is not None]
    return WalkForwardResult(
        fold_count=len(folds),
        positive_folds=sum(1 for fold in folds if fold.positive),
        sample_size=len(candidate_all),
        expectancy_r=round(expectancy, 8),
        profit_factor=round(aggregate_pf, 8) if aggregate_pf is not None else None,
        max_drawdown_r=round(_max_drawdown(candidate_all), 8),
        folds=tuple(folds),
        leakage_checks_passed=leakage_ok,
        reasons=tuple(reasons),
        positive_fold_ratio=sum(fold.positive for fold in folds) / len(folds) if folds else 0.0,
        worst_fold_expectancy=min(expectations) if expectations else None,
        worst_fold_profit_factor=min(fold_factors) if folds and len(fold_factors) == len(folds) else None,
        worst_fold_drawdown=max(fold.candidate_max_drawdown_r for fold in folds) if folds else None,
        median_fold_expectancy=median(expectations) if expectations else None,
        fold_dispersion=pstdev(expectations) if expectations else None,
        validation_returns_r=tuple(candidate_all),
        profit_factor_reason=("no_observed_losses" if candidate_all else "no_validation_observations") if aggregate_pf is None else None,
        worst_fold_profit_factor_reason="one_or_more_fold_factors_unavailable" if len(fold_factors) != len(folds) or not folds else None,
    )
