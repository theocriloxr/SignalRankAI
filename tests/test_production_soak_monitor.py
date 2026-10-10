"""Operational monitoring never invents financial or release-soak evidence."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.production_soak_monitor import evaluate_observation, summarize

SHA = "a" * 40


def baseline():
    config = {"release_sha": SHA, "schema_head": "0045", "environment_id": "production", "hours": 72,
              "services": {"worker": {"deployment_id": "approved-worker", "service_id": "worker-service"}}}
    health = {"status": "ready", "ready": True,
              "release_identity": {"confirmed": True, "deployed_git_sha": SHA, "expected_git_sha": SHA,
                                   "deployed_alembic_revision": "0045", "expected_alembic_revision": "0045"},
              "checks": {"financial_activation": {"ok": True, "requested": False, "live_execution_requested": False, "payouts_requested": False}}}
    services = {"worker": {"runtime": {"serviceId": "worker-service", "activeDeployments": [
                               {"id": "approved-worker", "status": "SUCCESS", "meta": {"commitHash": SHA},
                                "deploymentStopped": False, "instances": [{"id": "replica-1", "status": "RUNNING"},
                                                                         {"id": "old-replica", "status": "REMOVED"}]}]},
                           "deployments": [{"id": "approved-worker", "status": "SUCCESS", "meta": {"commitHash": SHA}},
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
    if defect == "deployment": services["worker"]["runtime"]["activeDeployments"][0]["status"] = "REMOVED"
    if defect == "overlap": services["worker"]["runtime"]["activeDeployments"].append(services["worker"]["runtime"]["activeDeployments"][0])
    if defect == "kill_switch": services["worker"]["variables"]["GLOBAL_EXECUTION_KILL_SWITCH"] = "0"
    if defect == "execution": services["worker"]["variables"]["REAL_EXECUTION_ENABLED"] = "1"
    if defect == "configuration": services["worker"].pop("variables")
    if defect == "readiness": health["ready"] = False
    if defect == "public_safety": health["checks"]["financial_activation"]["requested"] = True
    assert evaluate_observation(config, health, services)["readiness_ok"] is False


@pytest.mark.parametrize("defect", ["stopped", "crashed", "no_replicas", "unavailable", "wrong_service",
                                    "partial", "extra", "duplicate", "unknown", "missing_stopped", "invalid_target"])
def test_success_badge_cannot_hide_missing_or_failed_runtime(defect):
    config, health, services = baseline()
    runtime = services["worker"]["runtime"]
    deployment = runtime["activeDeployments"][0]
    if defect == "stopped": deployment["deploymentStopped"] = True
    if defect == "crashed": deployment["instances"][0]["status"] = "CRASHED"
    if defect == "no_replicas": deployment["instances"] = []
    if defect == "unavailable": services["worker"].pop("runtime")
    if defect == "wrong_service": runtime["serviceId"] = "another-service"
    if defect == "partial": config["services"]["worker"]["replicas"] = 2
    if defect == "extra": deployment["instances"].append({"id": "extra", "status": "RUNNING"})
    if defect == "duplicate": deployment["instances"].append(deployment["instances"][0])
    if defect == "unknown": deployment["instances"][0]["status"] = "UNKNOWN"
    if defect == "missing_stopped": deployment.pop("deploymentStopped")
    if defect == "invalid_target": config["services"]["worker"]["replicas"] = True
    result = evaluate_observation(config, health, services)
    assert result["readiness_ok"] is False
    assert "worker:running_replicas_not_proven" in result["failures"]


def test_runtime_is_authoritative_over_historical_success():
    config, health, services = baseline()
    services["worker"]["runtime"]["activeDeployments"] = []
    result = evaluate_observation(config, health, services)
    assert result["readiness_ok"] is False
    assert "worker:active_deployment_changed_or_missing" in result["failures"]


def test_all_configured_replicas_must_be_running():
    config, health, services = baseline()
    config["services"]["worker"]["replicas"] = 2
    services["worker"]["runtime"]["activeDeployments"][0]["instances"].append(
        {"id": "replica-2", "status": "RUNNING"})
    result = evaluate_observation(config, health, services)
    assert result["readiness_ok"] is True
    assert result["services"]["worker"]["running_replicas"] == 2


def test_collect_reads_active_replicas_and_never_exports_raw_variables(monkeypatch):
    from io import StringIO
    from scripts import production_soak_monitor as monitor

    config, health, services = baseline()
    config.update(project_id="project", railway_cli="railway", base_url="https://example.test")
    calls = []

    def cli_read(_config, command, *, input_text=None):
        calls.append((command, input_text))
        if command == ["api", "--compact"]:
            assert "activeDeployments" in input_text and "instances { id status }" in input_text
            assert 'serviceId:"worker-service"' in input_text
            return {"data": {"serviceInstance": services["worker"]["runtime"]}}
        assert command[:2] == ["variable", "list"]
        return services["worker"]["variables"]

    response = StringIO(json.dumps(health))
    response.status = 200
    monkeypatch.setattr(monitor, "urlopen", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(monitor, "_cli_json", cli_read)
    result = monitor.collect(config)
    assert result["readiness_ok"] is True
    assert len(calls) == 2
    assert "database-password-never-written" not in json.dumps(result)


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
