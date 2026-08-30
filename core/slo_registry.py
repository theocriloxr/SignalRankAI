"""SLO registry, error budgets and degradation decisions (V2.0 section 26).

Every SLO carries its owning service, targets, alert and an automatic
degradation response. The ``SloBudget`` tracker converts observed latency and
outcome samples into an error-rate and a typed degradation decision so a
budget-exhausted capability is degraded instead of left to fail unsafely.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class SloDefinition:
    name: str
    owning_service: str
    target: str
    error_budget_pct: float
    objective: float
    alert_threshold_pct: float
    degradation: str
    description: str


#: V2.0 section 26 SLO table.
SLO_REGISTRY: tuple[SloDefinition, ...] = (
    SloDefinition(
        "webhook_ack_p95", "frontdoor", "p95 < 500ms", 5.0, 0.95,
        0.03, "degrade_telegram_webhook_to_queue_only",
        "Telegram webhook acknowledgement latency p95 below 500ms.",
    ),
    SloDefinition(
        "webhook_ack_p99", "frontdoor", "p99 < 1s", 5.0, 0.99,
        0.03, "degrade_telegram_webhook_to_queue_only",
        "Telegram webhook acknowledgement latency p99 below 1 second.",
    ),
    SloDefinition(
        "signal_persistence_p99", "engine", "p99 < 2s", 5.0, 0.99,
        0.03, "pause_engine_scan_cycles",
        "Canonical signal persistence p99 below 2 seconds.",
    ),
    SloDefinition(
        "qualified_signal_delivery_p95", "delivery", "p95 < 5s", 5.0, 0.95,
        0.03, "disable_public_one_minute_delivery",
        "Qualified signal delivery p95 below 5 seconds.",
    ),
    SloDefinition(
        "outcome_detection_p95", "worker", "p95 < one tracker interval", 5.0, 0.95,
        0.03, "increase_tracker_interval_and_alert",
        "Outcome detection within one tracker interval.",
    ),
    SloDefinition(
        "notification_queue_age_p99", "notifications", "p99 < 60s", 5.0, 0.99,
        0.03, "throttle_fanout_and_backoff",
        "Notification queue age p99 below 60 seconds.",
    ),
    SloDefinition(
        "performance_projection_coverage", "ledger", ">= 99.9%", 0.1, 0.999,
        0.001, "pause_reconciliation_rebuilds",
        "Performance projection coverage at or above 99.9%.",
    ),
    SloDefinition(
        "outcome_projection_coverage", "outcomes", ">= 99.9%", 0.1, 0.999,
        0.001, "queue_outcome_outbox_repair",
        "Outcome projection coverage at or above 99.9%.",
    ),
)


def slo_by_name(name: str) -> SloDefinition | None:
    for slo in SLO_REGISTRY:
        if slo.name == name:
            return slo
    return None


@dataclass(frozen=True, slots=True)
class DegradationDecision:
    degraded: bool
    capability: str
    reason: str
    error_rate: float
    budget_remaining_pct: float
    slo: str


class SloBudget:
    """Small fixed-window error-budget tracker for one SLO."""

    def __init__(self, slo: SloDefinition, *, window: int = 1000) -> None:
        self.slo = slo
        self.window = max(100, int(window))
        self._outcomes: list[bool] = []
        self._latencies: list[float] = []
        self.started_at = time.monotonic()

    def record_success(self, *, latency_ms: float | None = None) -> None:
        self._outcomes.append(True)
        self._trim()
        if latency_ms is not None:
            self._latencies.append(max(0.0, float(latency_ms)))
            if len(self._latencies) > self.window:
                self._latencies = self._latencies[-self.window:]

    def record_failure(self, *, latency_ms: float | None = None) -> None:
        self._outcomes.append(False)
        self._trim()
        if latency_ms is not None:
            self._latencies.append(max(0.0, float(latency_ms)))
            if len(self._latencies) > self.window:
                self._latencies = self._latencies[-self.window:]

    def _trim(self) -> None:
        if len(self._outcomes) > self.window:
            self._outcomes = self._outcomes[-self.window:]

    def error_rate(self) -> float:
        if not self._outcomes:
            return 0.0
        return sum(0 if ok else 1 for ok in self._outcomes) / len(self._outcomes)

    def success_rate(self) -> float:
        return 1.0 - self.error_rate()

    def latency_percentile(self, percentile: float) -> float | None:
        if not self._latencies:
            return None
        ordered = sorted(self._latencies)
        index = min(len(ordered) - 1, max(0, int(math.ceil(float(percentile) * len(ordered))) - 1))
        return ordered[index]

    def budget_remaining_pct(self) -> float:
        """Percent of the error budget still available (>= 0)."""
        budget = max(1e-9, float(self.slo.error_budget_pct) / 100.0)
        return max(0.0, (budget - self.error_rate()) / budget) * 100.0

    def degraded(self) -> bool:
        return self.error_rate() > float(self.slo.alert_threshold_pct) / 100.0

    def decision(self) -> DegradationDecision:
        reason = (
            "error_budget_exhausted"
            if self.budget_remaining_pct() <= 0.0
            else "alert_threshold_exceeded"
            if self.degraded()
            else "healthy"
        )
        return DegradationDecision(
            degraded=reason != "healthy",
            capability=self.slo.name,
            reason=reason,
            error_rate=self.error_rate(),
            budget_remaining_pct=self.budget_remaining_pct(),
            slo=self.slo.description,
        )

    def snapshot(self) -> dict[str, float | str]:
        return {
            "slo": self.slo.name,
            "success_rate": self.success_rate(),
            "error_rate": self.error_rate(),
            "budget_remaining_pct": self.budget_remaining_pct(),
            "p95_ms": self.latency_percentile(0.95),
            "p99_ms": self.latency_percentile(0.99),
            "samples": len(self._outcomes),
        }


class SloRegistry:
    """Registry of live SLO budgets, one per definition, created lazily."""

    def __init__(self) -> None:
        self._budgets: dict[str, SloBudget] = {}

    def budget(self, name: str) -> SloBudget:
        slo = slo_by_name(name)
        if slo is None:
            raise KeyError(f"unknown_slo:{name}")
        budget = self._budgets.get(name)
        if budget is None:
            budget = SloBudget(slo)
            self._budgets[name] = budget
        return budget

    def decision(self, name: str) -> DegradationDecision:
        return self.budget(name).decision()

    def all_decisions(self) -> dict[str, DegradationDecision]:
        return {name: self.decision(name) for name in self._budgets}

    def snapshots(self) -> dict[str, dict[str, float | str]]:
        return {name: self.budget(name).snapshot() for name in self._budgets}


__all__ = [
    "DegradationDecision",
    "SLO_REGISTRY",
    "SloBudget",
    "SloDefinition",
    "SloRegistry",
    "slo_by_name",
]
