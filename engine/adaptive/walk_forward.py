from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Mapping, Sequence

from .dataset import AdaptiveDatasetRow


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
    candidate_profit_factor: float
    candidate_max_drawdown_r: float
    positive: bool


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    fold_count: int
    positive_folds: int
    sample_size: int
    expectancy_r: float
    profit_factor: float
    max_drawdown_r: float
    folds: tuple[WalkForwardFold, ...]
    leakage_checks_passed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["folds"] = [asdict(fold) for fold in self.folds]
        return payload


def _profit_factor(values: Sequence[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return wins / losses if losses else (999.0 if wins else 0.0)


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
    if _profit_factor(values) < 1.0:
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
    ordered = sorted(rows, key=lambda item: (item.decision_time, item.signal_id))
    reasons: list[str] = []
    if len(ordered) < minimum_train + validation_size:
        return WalkForwardResult(0, 0, len(ordered), 0.0, 0.0, 0.0, (), True, ("insufficient_chronological_rows",))
    regime_weights = regime_weights or {}
    folds: list[WalkForwardFold] = []
    candidate_all: list[float] = []
    cursor = minimum_train
    fold_number = 1
    while cursor + validation_size <= len(ordered):
        train = ordered[:cursor]
        validation_start = ordered[cursor].decision_time
        train_cutoff = validation_start - timedelta(seconds=max(0, embargo_seconds))
        purged_train = [row for row in train if row.decision_time < train_cutoff]
        validation = ordered[cursor : cursor + validation_size]
        if not purged_train or purged_train[-1].decision_time >= validation[0].decision_time:
            reasons.append(f"fold_{fold_number}_chronology_failed")
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
        positive = candidate_exp > baseline_exp and candidate_exp > 0 and pf >= 1.0
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
                candidate_profit_factor=round(pf, 8),
                candidate_max_drawdown_r=round(dd, 8),
                positive=positive,
            )
        )
        candidate_all.extend(candidate)
        cursor += validation_size
        fold_number += 1
    expectancy = sum(candidate_all) / len(candidate_all) if candidate_all else 0.0
    leakage_ok = not any("chronology_failed" in reason for reason in reasons)
    return WalkForwardResult(
        fold_count=len(folds),
        positive_folds=sum(1 for fold in folds if fold.positive),
        sample_size=len(candidate_all),
        expectancy_r=round(expectancy, 8),
        profit_factor=round(_profit_factor(candidate_all), 8),
        max_drawdown_r=round(_max_drawdown(candidate_all), 8),
        folds=tuple(folds),
        leakage_checks_passed=leakage_ok,
        reasons=tuple(reasons),
    )
