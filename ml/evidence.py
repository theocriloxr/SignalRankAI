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
        payload = self.to_dict()
        # Wall-clock creation time is metadata, not dataset identity.  It is
        # excluded so rerunning an identical manifest produces the same hash.
        payload.pop("created_at", None)
        return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


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


def _wilson_interval(successes: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    rate = max(0, min(total, successes)) / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    spread = z * ((rate * (1 - rate) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


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
    confidence_low, confidence_high = _wilson_interval(wins, n)
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


@dataclass(frozen=True, slots=True)
class PublicClaimDecision:
    certified: bool
    reasons: tuple[str, ...]
    metrics: PerformanceMetrics
    unique_theses: int
    delivered_signals: int
    terminal_signals: int
    outcome_coverage: float
    strict_tp3_win_rate: float
    strict_confidence_low: float


def evaluate_public_win_rate_claim(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    approved_drawdown_limit_r: float,
    minimum_win_rate_lower_bound: float = 0.70,
) -> PublicClaimDecision:
    """Certify a public win-rate claim from unique, delivered OOS theses only."""
    delivered = [row for row in outcomes if bool(row.get("delivered")) and bool(row.get("out_of_sample"))]
    thesis_ids = {str(row.get("thesis_fingerprint") or "") for row in delivered if row.get("thesis_fingerprint")}
    terminal_states = {"tp3", "stop_loss", "sl", "partial_profit", "breakeven", "expired", "cancelled", "data_unavailable"}
    seen: set[str] = set()
    terminal: list[Mapping[str, Any]] = []
    for row in delivered:
        thesis = str(row.get("thesis_fingerprint") or "")
        state = str(row.get("state") or row.get("outcome") or "").lower()
        if not thesis or thesis in seen or state not in terminal_states:
            continue
        seen.add(thesis)
        terminal.append(row)
    metrics = compute_metrics(terminal)
    strict_wins = sum(
        1
        for row in terminal
        if str(row.get("state") or row.get("outcome") or "").lower() == "tp3"
    )
    strict_rate = strict_wins / len(terminal) if terminal else 0.0
    strict_confidence_low = _wilson_interval(strict_wins, len(terminal))[0]
    coverage = len(terminal) / len(delivered) if delivered else 0.0
    reasons: list[str] = []
    if len(terminal) < 200:
        reasons.append("minimum_200_terminal_delivered_oos_signals")
    if len(thesis_ids) < 100:
        reasons.append("minimum_100_unique_theses")
    if coverage < 0.95:
        reasons.append("outcome_coverage_below_95_percent")
    if strict_confidence_low < minimum_win_rate_lower_bound:
        reasons.append("wilson_lower_bound_below_70_percent")
    if metrics.expectancy_r <= 0:
        reasons.append("non_positive_after_cost_expectancy")
    if metrics.profit_factor <= 1.0:
        reasons.append("profit_factor_not_positive")
    if metrics.max_drawdown_r > float(approved_drawdown_limit_r):
        reasons.append("approved_drawdown_limit_exceeded")
    return PublicClaimDecision(
        certified=not reasons,
        reasons=tuple(reasons),
        metrics=metrics,
        unique_theses=len(thesis_ids),
        delivered_signals=len(delivered),
        terminal_signals=len(terminal),
        outcome_coverage=coverage,
        strict_tp3_win_rate=strict_rate,
        strict_confidence_low=strict_confidence_low,
    )


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
    "PublicClaimDecision",
    "SCHEMA_VERSION",
    "build_manifest",
    "compute_metrics",
    "evaluate_promotion",
    "evaluate_public_win_rate_claim",
    "register_candidate",
    "purged_walk_forward_splits",
]
