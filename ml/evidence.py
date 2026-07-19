"""Reproducible backtest/WFO evidence and conservative promotion gates.

Pass 8 keeps historical performance claims separate from delivered/live
outcomes.  The helpers are pure and JSON-serialisable so a run can be stored
in an outbox or reviewed without importing a model framework.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "phase4-pass8-v1"


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    dataset_id: str
    dataset_hash: str
    provider: str
    start: str
    end: str
    strategy_version: str
    model_version: str | None
    prompt_version: str | None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    fill_assumptions: Mapping[str, Any] = field(default_factory=dict)
    code_commit: str | None = None
    trial_count: int = 1
    provenance: str = "backtest"
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict()).encode("utf-8")).hexdigest()


def build_manifest(
    *,
    dataset_id: str,
    rows: Iterable[Mapping[str, Any]] | None = None,
    provider: str = "unknown",
    start: str = "",
    end: str = "",
    strategy_version: str = "unknown",
    model_version: str | None = None,
    prompt_version: str | None = None,
    parameters: Mapping[str, Any] | None = None,
    fill_assumptions: Mapping[str, Any] | None = None,
    code_commit: str | None = None,
    trial_count: int = 1,
    provenance: str = "backtest",
) -> EvidenceManifest:
    normalized_rows = list(rows or [])
    dataset_hash = hashlib.sha256(_canonical({"dataset_id": dataset_id, "rows": normalized_rows}).encode("utf-8")).hexdigest()
    return EvidenceManifest(
        dataset_id=str(dataset_id),
        dataset_hash=dataset_hash,
        provider=str(provider),
        start=str(start),
        end=str(end),
        strategy_version=str(strategy_version),
        model_version=model_version,
        prompt_version=prompt_version,
        parameters=dict(parameters or {}),
        fill_assumptions=dict(fill_assumptions or {}),
        code_commit=code_commit,
        trial_count=max(1, int(trial_count)),
        provenance=str(provenance),
    )


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    sample_size: int
    wins: int
    losses: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_r: float
    tp1_rate: float = 0.0
    tp2_rate: float = 0.0
    tp3_rate: float = 0.0
    sl_rate: float = 0.0
    expired_rate: float = 0.0
    missed_entry_rate: float = 0.0
    total_cost_r: float = 0.0
    average_latency_ms: float = 0.0
    confidence_low: float = 0.0
    confidence_high: float = 0.0


def compute_metrics(outcomes: Sequence[Mapping[str, Any] | float]) -> PerformanceMetrics:
    values: list[float] = []
    tp_counts = {"tp1": 0, "tp2": 0, "tp3": 0}
    sl = expired = missed = 0
    costs: list[float] = []
    latencies: list[float] = []
    for item in outcomes:
        if isinstance(item, Mapping):
            raw = item.get("r_multiple", item.get("r", item.get("pnl", 0)))
            state = str(item.get("state", item.get("outcome", ""))).lower()
            try:
                costs.append(float(item.get("cost_r", item.get("cost", 0)) or 0.0))
                latencies.append(float(item.get("latency_ms", 0) or 0.0))
            except (TypeError, ValueError):
                pass
        else:
            raw, state = item, ""
        try:
            value = float(raw or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        values.append(value)
        for key in tp_counts:
            if key in state:
                tp_counts[key] += 1
        sl += int("sl" in state and "tp" not in state)
        expired += int("expired" in state or "time_stop" in state)
        missed += int("missed" in state)
    n = len(values)
    wins = sum(v > 0 for v in values)
    losses = sum(v < 0 for v in values)
    gross_win = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    # Wilson interval is deliberately conservative for sparse samples and is
    # suitable for public reports without claiming a point estimate is truth.
    if n:
        z = 1.96
        denominator = 1 + z * z / n
        centre = (wins / n + z * z / (2 * n)) / denominator
        spread = z * ((wins / n * (1 - wins / n) / n + z * z / (4 * n * n)) ** 0.5) / denominator
        confidence_low, confidence_high = max(0.0, centre - spread), min(1.0, centre + spread)
    else:
        confidence_low = confidence_high = 0.0
    return PerformanceMetrics(
        sample_size=n,
        wins=wins,
        losses=losses,
        win_rate=(wins / n if n else 0.0),
        expectancy_r=(mean(values) if values else 0.0),
        profit_factor=(gross_win / gross_loss if gross_loss else (float("inf") if gross_win else 0.0)),
        max_drawdown_r=drawdown,
        tp1_rate=(tp_counts["tp1"] / n if n else 0.0),
        tp2_rate=(tp_counts["tp2"] / n if n else 0.0),
        tp3_rate=(tp_counts["tp3"] / n if n else 0.0),
        sl_rate=(sl / n if n else 0.0),
        expired_rate=(expired / n if n else 0.0),
        missed_entry_rate=(missed / n if n else 0.0),
        total_cost_r=sum(costs),
        average_latency_ms=(mean(latencies) if latencies else 0.0),
        confidence_low=confidence_low,
        confidence_high=confidence_high,
    )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    eligible: bool
    status: str
    reasons: tuple[str, ...]
    metrics: PerformanceMetrics
    manifest_hash: str


def evaluate_promotion(
    manifest: EvidenceManifest,
    metrics: PerformanceMetrics,
    *,
    positive_folds: int = 0,
    drawdown_limit_r: float = 10.0,
    require_human_approval: bool = True,
    human_approved: bool = False,
) -> PromotionDecision:
    reasons: list[str] = []
    if manifest.provenance not in {"walk_forward", "shadow", "backtest"}:
        reasons.append("unsupported_provenance")
    if metrics.sample_size < 100:
        reasons.append("minimum_100_out_of_sample_trades")
    if positive_folds < 3:
        reasons.append("minimum_3_positive_wfo_folds")
    if metrics.expectancy_r <= 0:
        reasons.append("non_positive_expectancy")
    if metrics.profit_factor < 1.10:
        reasons.append("profit_factor_below_1_10")
    if metrics.max_drawdown_r > float(drawdown_limit_r):
        reasons.append("drawdown_limit_exceeded")
    if manifest.trial_count < 1:
        reasons.append("trial_count_missing")
    if require_human_approval and not human_approved:
        reasons.append("human_approval_required")
    eligible = not reasons
    return PromotionDecision(eligible, "ELIGIBLE" if eligible else "QUARANTINED", tuple(reasons), metrics, manifest.manifest_hash)


def register_candidate(manifest: EvidenceManifest, decision: PromotionDecision) -> dict[str, Any]:
    """Return an immutable candidate record; never changes the live champion."""
    return {
        "candidate_id": manifest.manifest_hash,
        "status": decision.status,
        "eligible": decision.eligible,
        "reasons": list(decision.reasons),
        "manifest": manifest.to_dict(),
        "metrics": asdict(decision.metrics),
        "requires_human_approval": True,
    }


def purged_walk_forward_splits(
    timestamps: Sequence[Any],
    *,
    train_size: int,
    test_size: int,
    embargo: int = 0,
) -> list[tuple[list[int], list[int]]]:
    """Build chronological train/test folds with an embargo gap.

    The function operates on indices, making it usable with pandas, NumPy, or
    plain records while guaranteeing no test row can leak into train data.
    """
    n = len(timestamps)
    if train_size <= 0 or test_size <= 0:
        return []
    folds: list[tuple[list[int], list[int]]] = []
    start = 0
    while start + train_size + embargo + test_size <= n:
        train = list(range(start, start + train_size))
        test_start = start + train_size + max(0, embargo)
        test = list(range(test_start, test_start + test_size))
        folds.append((train, test))
        start += test_size
    return folds


__all__ = [
    "EvidenceManifest",
    "PerformanceMetrics",
    "PromotionDecision",
    "SCHEMA_VERSION",
    "build_manifest",
    "compute_metrics",
    "evaluate_promotion",
    "register_candidate",
    "purged_walk_forward_splits",
]
