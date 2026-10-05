from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import approve_production_release as release
from scripts import assert_database_schema as schema

SHA = "a" * 40
ENV = {"GITHUB_SHA": SHA, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
       "GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": release.REPOSITORY,
       "GITHUB_REF": f"refs/heads/{release.BRANCH}"}


class FakeAPIs:
    def __init__(self):
        self.run = {"head_sha": SHA, "head_branch": release.BRANCH, "event": "push",
                    "path": ".github/workflows/ci.yml", "run_attempt": 2,
                    "head_repository": {"full_name": release.REPOSITORY}}
        self.jobs = [{"name": name, "status": "completed", "conclusion": "success"}
                     for name in sorted(release.REQUIRED_JOBS)]
        self.head = SHA
        self.calls = []
        self.check_suites = True
        self.deploy_result = True
        self.patch_result = "change-id"
        self.trigger_reads = 0
        self.advance_on_last_read = False
        self.variables = {"GLOBAL_EXECUTION_KILL_SWITCH": "1"}

    def github(self, path):
        if path.startswith("git/ref/"):
            return {"object": {"sha": self.head}}
        if "/jobs?" in path:
            return {"jobs": self.jobs, "total_count": len(self.jobs)}
        assert path == "actions/runs/123/attempts/2"
        return self.run

    def railway(self, query, variables):
        self.calls.append((query, deepcopy(variables)))
        if "deploymentTriggers" in query:
            self.trigger_reads += 1
            if self.advance_on_last_read and self.trigger_reads == 4:
                self.head = "b" * 40
            return {"variables": self.variables, "deploymentTriggers": {"edges": [{"node": {
                "branch": release.BRANCH, "repository": release.REPOSITORY,
                "checkSuites": self.check_suites,
            }}]}}
        if "environmentPatchCommit" in query:
            return {"environmentPatchCommit": self.patch_result}
        return {"serviceInstanceDeploy": self.deploy_result}


def mutations(api):
    return [(query, variables) for query, variables in api.calls if query.startswith("mutation")]


def test_exact_passing_release_updates_all_pins_before_any_deploy():
    api = FakeAPIs()
    assert release.approve(api, ENV) == SHA
    calls = mutations(api)
    assert len(calls) == 5
    query, variables = calls[0]
    assert "skipDeploys:true" in query
    assert set(variables["patch"]["services"]) == set(release.SERVICES.values())
    for service in variables["patch"]["services"].values():
        assert service["variables"] == {
            "EXPECTED_RELEASE_COMMIT": {"value": SHA},
            "EXPECTED_RELEASE_BRANCH": {"value": release.BRANCH},
            "EXPECTED_ALEMBIC_HEAD": {"value": schema._expected_head()},
        }
    for query, variables in calls[1:]:
        assert "latestCommit:false" in query
        assert variables["sha"] == SHA
        assert variables["environment"] == release.ENVIRONMENT
    assert {v["service"] for _, v in calls[1:]} == set(release.SERVICES.values())


@pytest.mark.parametrize("key,value", [
    ("GITHUB_SHA", "a" * 8), ("GITHUB_RUN_ID", ""), ("GITHUB_RUN_ATTEMPT", "x"),
    ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/main"),
    ("GITHUB_REPOSITORY", "attacker/fork"),
])
def test_untrusted_invocation_cannot_mutate_production(key, value):
    api = FakeAPIs()
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, {**ENV, key: value})
    assert not api.calls


@pytest.mark.parametrize("key,value", [
    ("head_sha", "b" * 40), ("head_branch", "main"), ("event", "pull_request"),
    ("path", ".github/workflows/unrelated.yml"), ("run_attempt", 1),
    ("head_repository", {"full_name": "attacker/fork"}),
])
def test_wrong_run_provenance_is_rejected(key, value):
    api = FakeAPIs()
    api.run[key] = value
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not api.calls


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", None])
def test_every_required_job_must_pass(conclusion):
    api = FakeAPIs()
    api.jobs[0]["conclusion"] = conclusion
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not api.calls


@pytest.mark.parametrize("change", ["missing", "duplicate", "running"])
def test_incomplete_or_ambiguous_jobs_are_rejected(change):
    api = FakeAPIs()
    if change == "missing":
        api.jobs.pop()
    elif change == "duplicate":
        api.jobs.append(deepcopy(api.jobs[0]))
    else:
        api.jobs[0]["status"] = "in_progress"
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not api.calls


@pytest.mark.parametrize("during_reads", [False, True])
def test_superseded_run_cannot_roll_production_back(during_reads):
    api = FakeAPIs()
    if during_reads:
        api.advance_on_last_read = True
    else:
        api.head = "b" * 40
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not mutations(api)


def test_wait_for_ci_is_required():
    api = FakeAPIs()
    api.check_suites = False
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not mutations(api)


@pytest.mark.parametrize("flag", release.FINANCIAL_FLAGS)
def test_live_money_cannot_inherit_source_only_ci_approval(flag):
    api = FakeAPIs()
    api.variables[flag] = "true"
    with pytest.raises(release.PromotionBlocked, match="separately certified"):
        release.approve(api, ENV)
    assert not mutations(api)


@pytest.mark.parametrize("variables", [None, {}, {"GLOBAL_EXECUTION_KILL_SWITCH": "0"},
    {"GLOBAL_EXECUTION_KILL_SWITCH": "1", "REAL_EXECUTION_ENABLED": "unresolved-reference"}])
def test_unknown_or_unprotected_financial_state_blocks_promotion(variables):
    api = FakeAPIs()
    api.variables = variables
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert not mutations(api)


def test_unconfirmed_pin_update_never_requests_deployment():
    api = FakeAPIs()
    api.patch_result = None
    with pytest.raises(release.PromotionBlocked):
        release.approve(api, ENV)
    assert len(mutations(api)) == 1


def test_partial_deployment_failure_is_reported_not_certified():
    api = FakeAPIs()
    api.deploy_result = False
    with pytest.raises(release.PromotionBlocked, match="frontdoor"):
        release.approve(api, ENV)
    assert len(mutations(api)) == 2


def test_api_error_does_not_expose_credentials(monkeypatch, capsys):
    monkeypatch.setenv("GH_TOKEN", "private-gh-value")
    monkeypatch.setenv("RAILWAY_PRODUCTION_TOKEN", "private-railway-value")
    monkeypatch.setattr(release, "request_json", lambda *a: {"errors": [{"message": "private-value"}]})
    with pytest.raises(release.PromotionBlocked) as error:
        release.APIs().railway("query", {})
    assert "private" not in str(error.value) + capsys.readouterr().out


def test_migration_wait_rechecks_then_admits(monkeypatch):
    reports = iter([{"ok": False}, {"ok": True}])
    clock = iter([0, 0, 5])
    sleeps = []
    monkeypatch.setattr(schema, "check_schema", lambda: next(reports))
    monkeypatch.setattr(schema.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(schema.time, "sleep", sleeps.append)
    assert schema.wait_for_schema(10) == ({"ok": True}, 0)
    assert sleeps == [5]


def test_migration_wait_expires_closed(monkeypatch):
    clock = iter([0, 10])
    monkeypatch.setattr(schema.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(schema, "check_schema", lambda: {"ok": False})
    assert schema.wait_for_schema(10)[1] == schema.EXIT_SCHEMA_MISMATCH


def test_schema_configuration_error_is_not_retried(monkeypatch):
    def invalid():
        raise RuntimeError("invalid schema configuration")
    monkeypatch.setattr(schema, "check_schema", invalid)
    monkeypatch.setattr(schema.time, "sleep", lambda _: pytest.fail("configuration cannot recover by waiting"))
    assert schema.wait_for_schema(600)[1] == schema.EXIT_CONFIGURATION


def test_no_wait_keeps_original_fail_fast_behavior(monkeypatch):
    monkeypatch.setattr(schema, "check_schema", lambda: {"ok": False})
    assert schema.wait_for_schema()[1] == schema.EXIT_SCHEMA_MISMATCH
