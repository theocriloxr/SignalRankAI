"""Operational SLO alert ownership and escalation policy.

This module deliberately imports the canonical SLO registry instead of defining
another SLO taxonomy. Tests require exact one-to-one coverage so monitoring,
alert ownership, degradation actions and runbooks cannot drift from runtime
semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.slo_registry import SLO_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = "docs/runbooks/SLO_ERROR_BUDGET_INCIDENT_RESPONSE.md"
PROMETHEUS_RULES_PATH = "observability/prometheus/signalrank-slo-alerts.yml"
GRAFANA_DASHBOARD_PATH = "observability/grafana/signalrank-slo-overview.json"


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    slo: str
    owner: str
    warning_budget_remaining_pct: float
    critical_budget_remaining_pct: float
    warning_min_samples: int
    critical_min_samples: int
    warning_for: str
    critical_for: str
    runbook: str
    automatic_action: str


def _policy(
    slo: str,
    owner: str,
    automatic_action: str,
    *,
    warning_budget_remaining_pct: float = 50.0,
    critical_budget_remaining_pct: float = 0.0,
    warning_min_samples: int = 50,
    critical_min_samples: int = 100,
    warning_for: str = "5m",
    critical_for: str = "2m",
) -> AlertPolicy:
    return AlertPolicy(
        slo=slo,
        owner=owner,
        warning_budget_remaining_pct=warning_budget_remaining_pct,
        critical_budget_remaining_pct=critical_budget_remaining_pct,
        warning_min_samples=warning_min_samples,
        critical_min_samples=critical_min_samples,
        warning_for=warning_for,
        critical_for=critical_for,
        runbook=RUNBOOK_PATH,
        automatic_action=automatic_action,
    )


ALERT_POLICIES: dict[str, AlertPolicy] = {
    "webhook_ack_p95": _policy(
        "webhook_ack_p95",
        "frontdoor",
        "degrade_telegram_webhook_to_queue_only",
    ),
    "webhook_ack_p99": _policy(
        "webhook_ack_p99",
        "frontdoor",
        "degrade_telegram_webhook_to_queue_only",
    ),
    "signal_persistence_p99": _policy(
        "signal_persistence_p99",
        "engine",
        "pause_engine_scan_cycles",
    ),
    "qualified_signal_delivery_p95": _policy(
        "qualified_signal_delivery_p95",
        "delivery",
        "disable_public_one_minute_delivery",
    ),
    "outcome_detection_p95": _policy(
        "outcome_detection_p95",
        "worker",
        "increase_tracker_interval_and_alert",
    ),
    "notification_queue_age_p99": _policy(
        "notification_queue_age_p99",
        "notifications",
        "throttle_fanout_and_backoff",
    ),
    "performance_projection_coverage": _policy(
        "performance_projection_coverage",
        "ledger",
        "pause_reconciliation_rebuilds",
    ),
    "outcome_projection_coverage": _policy(
        "outcome_projection_coverage",
        "outcomes",
        "queue_outcome_outbox_repair",
    ),
}


def validate_alert_policies() -> tuple[str, ...]:
    """Return contract violations; an empty tuple means operational coverage is complete."""
    problems: list[str] = []
    definitions = {definition.name: definition for definition in SLO_REGISTRY}
    policy_names = set(ALERT_POLICIES)
    definition_names = set(definitions)

    for missing in sorted(definition_names - policy_names):
        problems.append(f"missing_alert_policy:{missing}")
    for extra in sorted(policy_names - definition_names):
        problems.append(f"unknown_alert_policy:{extra}")

    for name in sorted(definition_names & policy_names):
        definition = definitions[name]
        policy = ALERT_POLICIES[name]
        if policy.owner != definition.owning_service:
            problems.append(
                f"owner_mismatch:{name}:{policy.owner}!={definition.owning_service}"
            )
        if policy.automatic_action != definition.degradation:
            problems.append(
                f"degradation_mismatch:{name}:{policy.automatic_action}!={definition.degradation}"
            )
        if policy.warning_budget_remaining_pct <= policy.critical_budget_remaining_pct:
            problems.append(f"invalid_budget_thresholds:{name}")
        if policy.warning_min_samples < 1 or policy.critical_min_samples < policy.warning_min_samples:
            problems.append(f"invalid_sample_thresholds:{name}")
        if not policy.runbook or not (ROOT / policy.runbook).exists():
            problems.append(f"missing_runbook:{name}:{policy.runbook}")

    for artifact in (PROMETHEUS_RULES_PATH, GRAFANA_DASHBOARD_PATH):
        if not (ROOT / artifact).exists():
            problems.append(f"missing_observability_artifact:{artifact}")
    return tuple(problems)


def policy_by_slo(name: str) -> AlertPolicy:
    try:
        return ALERT_POLICIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown_slo_alert_policy:{name}") from exc


__all__ = [
    "ALERT_POLICIES",
    "AlertPolicy",
    "GRAFANA_DASHBOARD_PATH",
    "PROMETHEUS_RULES_PATH",
    "RUNBOOK_PATH",
    "policy_by_slo",
    "validate_alert_policies",
]
