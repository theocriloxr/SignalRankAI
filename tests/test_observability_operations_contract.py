from __future__ import annotations

import json
from pathlib import Path

from core.slo_registry import SLO_REGISTRY
from observability.slo_operations import (
    ALERT_POLICIES,
    GRAFANA_DASHBOARD_PATH,
    PROMETHEUS_RULES_PATH,
    RUNBOOK_PATH,
    validate_alert_policies,
)


ROOT = Path(__file__).resolve().parents[1]


def test_every_canonical_slo_has_exact_operational_alert_ownership() -> None:
    assert validate_alert_policies() == ()
    definitions = {item.name: item for item in SLO_REGISTRY}
    assert set(ALERT_POLICIES) == set(definitions)

    for name, definition in definitions.items():
        policy = ALERT_POLICIES[name]
        assert policy.owner == definition.owning_service
        assert policy.automatic_action == definition.degradation
        assert policy.warning_budget_remaining_pct == 50.0
        assert policy.critical_budget_remaining_pct == 0.0
        assert policy.warning_min_samples == 50
        assert policy.critical_min_samples == 100
        assert policy.warning_for == "5m"
        assert policy.critical_for == "2m"
        assert policy.runbook == RUNBOOK_PATH


def test_prometheus_alert_rules_use_live_signalrank_metrics_and_runbook() -> None:
    rules = (ROOT / PROMETHEUS_RULES_PATH).read_text(encoding="utf-8")
    for alert in (
        "SignalRankSLOBudgetWarning",
        "SignalRankSLOBudgetCritical",
        "SignalRankServiceDown",
        "SignalRankProviderAPIUnhealthy",
    ):
        assert f"alert: {alert}" in rules

    for metric in (
        "signalrank_slo_samples",
        "signalrank_slo_budget_remaining_pct",
        "signalrank_slo_degraded",
        "signalrank_service_up",
        "signalrank_exchange_api_health",
    ):
        assert metric in rules

    assert "signalrank_slo_samples >= 50" in rules
    assert "signalrank_slo_samples >= 100" in rules
    assert "docs/runbooks/SLO_ERROR_BUDGET_INCIDENT_RESPONSE.md" in rules
    assert "owner: '{{ $labels.service }}'" in rules


def test_grafana_dashboard_is_valid_and_covers_core_slo_views() -> None:
    dashboard = json.loads((ROOT / GRAFANA_DASHBOARD_PATH).read_text(encoding="utf-8"))
    assert dashboard["uid"] == "signalrank-slo-overview"
    assert dashboard["refresh"] == "30s"
    assert "slo" in {str(tag).lower() for tag in dashboard["tags"]}

    expressions = {
        target.get("expr")
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    assert "min(signalrank_slo_budget_remaining_pct) by (slo, service)" in expressions
    assert "signalrank_slo_budget_remaining_pct" in expressions
    assert "signalrank_slo_error_rate" in expressions
    assert "signalrank_slo_samples" in expressions
    assert "signalrank_slo_degraded" in expressions
    assert "signalrank_service_up" in expressions
    assert "signalrank_exchange_api_health" in expressions


def test_incident_runbook_names_every_slo_owner_action_and_safety_boundary() -> None:
    runbook = (ROOT / RUNBOOK_PATH).read_text(encoding="utf-8")
    for definition in SLO_REGISTRY:
        assert f"`{definition.name}`" in runbook
        assert definition.owning_service in runbook
        assert f"`{definition.degradation}`" in runbook

    assert "Never enable real execution" in runbook
    assert "loosen a hard risk ceiling" in runbook
    assert "no safety gate was weakened" in runbook
    assert "stable or recovering for at least 15 minutes" in runbook
