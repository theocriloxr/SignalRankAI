"""Operational monitoring never invents financial or release-soak evidence."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.production_soak_monitor import evaluate_observation, summarize

SHA = "a" * 40


def baseline():
    config = {"release_sha": SHA, "schema_head": "0045", "environment_id": "production", "hours": 72,
              "services": {"worker": {"deployment_id": "approved-worker"}}}
    health = {"status": "ready", "ready": True,
              "release_identity": {"confirmed": True, "deployed_git_sha": SHA, "expected_git_sha": SHA,
                                   "deployed_alembic_revision": "0045", "expected_alembic_revision": "0045"},
              "checks": {"financial_activation": {"ok": True, "requested": False, "live_execution_requested": False, "payouts_requested": False}}}
    services = {"worker": {"deployments": [{"id": "approved-worker", "status": "SUCCESS", "meta": {"commitHash": SHA}},
                                          {"id": "rejected-candidate", "status": "FAILED", "meta": {"commitHash": "b" * 40}}],
                           "variables": {"EXPECTED_RELEASE_COMMIT": SHA, "GLOBAL_EXECUTION_KILL_SWITCH": "1",
                                         "DATABASE_URL": "database-password-never-written"}}}
    return config, health, services


def test_rejected_candidate_preserves_active_approved_baseline_and_secrets_stay_private():
    config, health, services = baseline()
    result = evaluate_observation(config, health, services)
    assert result["readiness_ok"] is True
    assert "database-password-never-written" not in json.dumps(result)


@pytest.mark.parametrize("defect", ["release", "schema", "deployment", "overlap", "kill_switch", "execution", "configuration", "readiness", "public_safety"])
def test_changed_or_unavailable_production_observation_is_not_healthy(defect):
    config, health, services = baseline()
    if defect == "release": health["release_identity"]["deployed_git_sha"] = "b" * 40
    if defect == "schema": health["release_identity"]["deployed_alembic_revision"] = "0048"
    if defect == "deployment": services["worker"]["deployments"][0]["status"] = "REMOVED"
    if defect == "overlap": services["worker"]["deployments"].append(services["worker"]["deployments"][0])
    if defect == "kill_switch": services["worker"]["variables"]["GLOBAL_EXECUTION_KILL_SWITCH"] = "0"
    if defect == "execution": services["worker"]["variables"]["REAL_EXECUTION_ENABLED"] = "1"
    if defect == "configuration": services["worker"].pop("variables")
    if defect == "readiness": health["ready"] = False
    if defect == "public_safety": health["checks"]["financial_activation"]["requested"] = True
    assert evaluate_observation(config, health, services)["readiness_ok"] is False


def test_complete_availability_window_cannot_become_financial_or_release_soak_certification():
    config, health, services = baseline()
    now = datetime.now(timezone.utc)
    observation = evaluate_observation(config, health, services)
    samples = [{**observation, "observed_at": (now - timedelta(hours=24) + timedelta(minutes=3*i)).isoformat()} for i in range(481)]
    report = summarize(samples, config, now=now)
    assert report["availability_window_24h_passed"] is True
    assert report["target_availability_window_passed"] is False
    assert report["release_soak_certified"] is False
    assert report["financial_readiness_certified"] is False
    samples.pop(100)
    assert summarize(samples, config, now=now)["availability_window_24h_passed"] is False


def test_configuration_changes_interrupt_availability_claim():
    config, health, services = baseline()
    first = evaluate_observation(config, health, services)
    services["worker"]["variables"]["DATABASE_URL"] = "different-secret"
    second = evaluate_observation(config, health, services)
    now = datetime.now(timezone.utc)
    samples = [{**first, "observed_at": (now - timedelta(minutes=3)).isoformat()}, {**second, "observed_at": now.isoformat()}]
    assert summarize(samples, config, now=now)["configuration_stable"] is False
