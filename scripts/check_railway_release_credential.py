#!/usr/bin/env python3
"""Read-only GitHub Actions check for the scoped production Railway token."""
from __future__ import annotations

import sys

from scripts.approve_production_release import (
    APIs, BRANCH, ENVIRONMENT, PROJECT, REPOSITORY, SERVICES,
    PromotionBlocked, require_paper_release_state,
)


def check(api: APIs) -> None:
    scope = api.railway("query { projectToken { projectId environmentId } }", {})
    token = scope.get("projectToken")
    if not isinstance(token, dict) or token.get("projectId") != PROJECT or token.get("environmentId") != ENVIRONMENT:
        raise PromotionBlocked("Railway project token is not scoped to the production environment")
    for role, service in SERVICES.items():
        data = api.railway("""query($project: String!, $environment: String!, $service: String!) {
          deploymentTriggers(projectId:$project, environmentId:$environment, serviceId:$service, first:10) {
            edges { node { branch repository checkSuites } }
          }
          variables(projectId:$project, environmentId:$environment, serviceId:$service)
        }""", {"project": PROJECT, "environment": ENVIRONMENT, "service": service})
        edges = (data.get("deploymentTriggers") or {}).get("edges")
        triggers = [edge.get("node") for edge in edges] if isinstance(edges, list) else []
        if (len(triggers) != 1 or not isinstance(triggers[0], dict)
                or triggers[0].get("branch") != BRANCH
                or triggers[0].get("repository") != REPOSITORY
                or triggers[0].get("checkSuites") is not True):
            raise PromotionBlocked(f"{role}: source branch / Wait for CI configuration differs")
        require_paper_release_state(data.get("variables"), role)


def main() -> int:
    try:
        check(APIs())
    except PromotionBlocked as exc:
        print(f"RAILWAY_CREDENTIAL_PREFLIGHT_BLOCKED: {exc}", file=sys.stderr)
        return 1
    print("RAILWAY_CREDENTIAL_PREFLIGHT_PASS: project, environment and four paper-release roles verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
