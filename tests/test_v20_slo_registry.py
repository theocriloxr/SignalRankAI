"""Regression tests: V2.0 SLO registry and error budgets."""
from __future__ import annotations

import pytest

from core.slo_registry import SLO_REGISTRY, SloBudget, SloDefinition, SloRegistry, slo_by_name


def test_registry_contains_section26_slos() -> None:
    names = {slo.name for slo in SLO_REGISTRY}
    assert {
        "webhook_ack_p95",
        "webhook_ack_p99",
        "signal_persistence_p99",
        "qualified_signal_delivery_p95",
        "notification_queue_age_p99",
        "performance_projection_coverage",
        "outcome_projection_coverage",
    } <= names


def test_slo_lookup() -> None:
    assert slo_by_name("webhook_ack_p95") is not None
    assert slo_by_name("missing_slo") is None


def test_budget_healthy_with_no_samples() -> None:
    budget = SloBudget(slo_by_name("webhook_ack_p95"))  # type: ignore[arg-type]
    decision = budget.decision()
    assert not decision.degraded
    assert decision.reason == "healthy"
    assert budget.error_rate() == 0.0


def test_budget_degrades_when_error_rate_exceeds_threshold() -> None:
    slo = SloDefinition(
        name="test", owning_service="x", target="p95 < 100ms",
        error_budget_pct=5.0, objective=0.95, alert_threshold_pct=3.0,
        degradation="degrade_test", description="test",
    )
    budget = SloBudget(slo, window=100)
    for _ in range(96):
        budget.record_success()
    for _ in range(4):  # 4% error > 3% alert threshold but within the 5% budget
        budget.record_failure()
    decision = budget.decision()
    assert decision.degraded
    assert decision.reason == "alert_threshold_exceeded"


def test_budget_exhaustion_decision() -> None:
    slo = SloDefinition(
        name="test2", owning_service="x", target="coverage >= 99%",
        error_budget_pct=1.0, objective=0.99, alert_threshold_pct=0.5,
        degradation="degrade_test", description="test",
    )
    budget = SloBudget(slo, window=100)
    for _ in range(60):
        budget.record_failure()  # 60% error, budget (1%) fully consumed
    decision = budget.decision()
    assert decision.degraded
    assert decision.reason == "error_budget_exhausted"
    assert decision.budget_remaining_pct <= 0.0


def test_budget_latency_percentiles() -> None:
    budget = SloBudget(slo_by_name("webhook_ack_p95"))  # type: ignore[arg-type]
    for i in range(1, 11):
        budget.record_success(latency_ms=float(i))
    p95 = budget.latency_percentile(0.95)
    assert p95 is not None
    assert 9.0 <= p95 <= 10.0
    p99 = budget.latency_percentile(0.99)
    assert p99 == 10.0


def test_registry_lazy_budget_creation() -> None:
    registry = SloRegistry()
    budget = registry.budget("webhook_ack_p95")
    assert registry.budget("webhook_ack_p95") is budget
    assert "webhook_ack_p95" in registry.snapshots()


def test_registry_unknown_slo_raises() -> None:
    registry = SloRegistry()
    with pytest.raises(KeyError):
        registry.budget("missing")
