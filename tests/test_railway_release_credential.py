from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import approve_production_release as release
from scripts import check_railway_release_credential as preflight


class ReadOnlyAPI:
    def __init__(self):
        self.scope = {"projectId": release.PROJECT, "environmentId": release.ENVIRONMENT}
        self.variables = {"GLOBAL_EXECUTION_KILL_SWITCH": "1", "REAL_EXECUTION_ENABLED": "0"}
        self.triggers = [{"node": {"branch": release.BRANCH, "repository": release.REPOSITORY,
                                   "checkSuites": True}}]
        self.calls = []

    def railway(self, query, variables):
        self.calls.append((query, deepcopy(variables)))
        if "projectToken" in query:
            return {"projectToken": self.scope}
        return {"deploymentTriggers": {"edges": self.triggers}, "variables": self.variables}


def test_scoped_token_and_safe_triggers_are_read_only():
    api = ReadOnlyAPI()
    preflight.check(api)
    assert len(api.calls) == 1 + len(release.SERVICES)
    assert all(query.lstrip().startswith("query") for query, _ in api.calls)


@pytest.mark.parametrize("scope", [None, {},
    {"projectId": "wrong", "environmentId": release.ENVIRONMENT},
    {"projectId": release.PROJECT, "environmentId": "wrong"}])
def test_wrong_or_unavailable_scope_blocks(scope):
    api = ReadOnlyAPI()
    api.scope = scope
    with pytest.raises(release.PromotionBlocked, match="not scoped"):
        preflight.check(api)
    assert len(api.calls) == 1


@pytest.mark.parametrize("defect", ["wrong_branch", "no_wait_for_ci", "missing_kill_switch", "live_execution"])
def test_unsafe_service_configuration_blocks_without_mutation(defect):
    api = ReadOnlyAPI()
    if defect == "wrong_branch":
        api.triggers[0]["node"]["branch"] = "main"
    elif defect == "no_wait_for_ci":
        api.triggers[0]["node"]["checkSuites"] = False
    elif defect == "missing_kill_switch":
        api.variables.pop("GLOBAL_EXECUTION_KILL_SWITCH")
    else:
        api.variables["REAL_EXECUTION_ENABLED"] = "1"
    with pytest.raises(release.PromotionBlocked):
        preflight.check(api)
    assert all(query.lstrip().startswith("query") for query, _ in api.calls)
