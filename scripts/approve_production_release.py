#!/usr/bin/env python3
"""Advance Railway's source pins only after this push's CI gates succeed.

The final CI job queues exact-commit deployments without waiting for them:
Railway's Wait for CI releases them after this workflow completes. Database
backup, schema, readiness and financial admission remain runtime gates.
"""
from __future__ import annotations

import json
import ast
import configparser
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPOSITORY = "theocriloxr/SignalRankAI"
BRANCH = "fix/provider-discovery-readiness-20260923"
PROJECT = "5baa1c14-a748-4dc8-8eb6-411c621e56c3"
ENVIRONMENT = "05a014d1-73c1-485c-b767-e734c7ea2877"
SERVICES = {
    "frontdoor": "60ad5d9b-02af-40ec-a677-6ce574c2ba09",
    "worker": "2f71448c-6218-4355-abd0-381d8dfdc241",
    "engine": "437eef9d-c41a-43d1-b41e-eb788b51c072",
    "analytics": "b0833ab8-04cb-4c88-a764-d527bbde93c7",
}
REQUIRED_JOBS = {
    "manifest", "static-quality-checks", "backend (3.11)", "backend (3.12)",
    "frontend", "mobile", "railway-credential-preflight", "release-certification",
}
FINANCIAL_FLAGS = (
    "LIVE_FINANCIAL_FEATURES_ENABLED", "REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED", "PROP_EXECUTION_ENABLED", "REAL_PAYOUTS_ENABLED",
    "MT5_ALLOW_LIVE_ACCOUNTS", "MT5_LIVE_EXECUTION_ENABLED", "MT5_AUTO_EXECUTION_ENABLED",
    "BYBIT_EXECUTION_ENABLED", "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
)


def require_paper_release_state(variables, role):
    # A source-only CI approval cannot renew a previous real-money approval.
    # Read rendered values in memory and never include them in logs or receipts.
    if not isinstance(variables, dict):
        raise PromotionBlocked(f"{role}: financial release state is unavailable")
    def normalized(key, default=""):
        return str(variables.get(key, default)).strip().strip('"').strip("'").lower()
    if normalized("GLOBAL_EXECUTION_KILL_SWITCH") not in {"1", "true", "yes", "on", "y"}:
        raise PromotionBlocked(f"{role}: automatic source promotion requires the execution kill switch")
    if any(normalized(flag, "0") not in {"0", "false", "no", "off", "n", ""} for flag in FINANCIAL_FLAGS):
        raise PromotionBlocked(f"{role}: live-money configuration requires a separately certified release")


def repository_schema_head():
    """Read migration metadata without importing application code or credentials."""
    revisions, parents = set(), set()
    root = Path(__file__).resolve().parents[1]
    config = configparser.ConfigParser()
    config.read(root / "alembic.ini")
    migrations = root / config.get("alembic", "script_location") / "versions"
    for path in migrations.glob("*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    if value is None:
                        raise PromotionBlocked("Migration metadata is missing a value")
                    metadata = ast.literal_eval(value)
                    if target.id == "revision":
                        revisions.add(metadata)
                    elif isinstance(metadata, str):
                        parents.add(metadata)
                    elif metadata is not None:
                        parents.update(metadata)
    heads = revisions - parents
    if len(heads) != 1 or not all(isinstance(head, str) and head for head in heads):
        raise PromotionBlocked("Repository must have one database migration head")
    return heads.pop()


class PromotionBlocked(RuntimeError):
    pass


def request_json(url, headers, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "SignalRankAI-ReleasePreflight/1.0",
        **headers,
    })
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310 -- fixed HTTPS API origins
            return json.load(response)
    except HTTPError as exc:
        # The numeric status identifies credential/scope failures safely. Never
        # include the response body, request URL, headers or API error text.
        raise PromotionBlocked(f"API request failed (HTTP {exc.code})") from None
    except (URLError, TimeoutError, ValueError) as exc:
        # API response bodies and URLs can contain credentials: never log them.
        raise PromotionBlocked(f"API request failed ({type(exc).__name__})") from None


class APIs:
    def __init__(self):
        self.github_token = os.environ.get("GH_TOKEN", "")
        self.railway_token = os.environ.get("RAILWAY_PRODUCTION_TOKEN", "")
        if not self.github_token or not self.railway_token:
            raise PromotionBlocked("GitHub and production-scoped Railway credentials are required")

    def github(self, path):
        return request_json(f"https://api.github.com/repos/{REPOSITORY}/{path}", {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def railway(self, query, variables):
        result = request_json("https://backboard.railway.com/graphql/v2", {
            "Project-Access-Token": self.railway_token,
        }, {"query": query, "variables": variables})
        if result.get("errors") or not isinstance(result.get("data"), dict):
            raise PromotionBlocked("Railway rejected the release operation")
        return result["data"]


def validate_ci(api, env):
    sha = env.get("GITHUB_SHA", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    if (env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_EVENT_NAME") != "push"
            or env.get("GITHUB_REF") != f"refs/heads/{BRANCH}"
            or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not run_id.isdigit() or not attempt.isdigit()):
        raise PromotionBlocked("Only an exact push on the production source branch may promote")
    run = api.github(f"actions/runs/{run_id}/attempts/{attempt}")
    if (run.get("head_sha") != sha or run.get("head_branch") != BRANCH
            or run.get("event") != "push" or run.get("path") != ".github/workflows/ci.yml"
            or run.get("head_repository", {}).get("full_name") != REPOSITORY
            or run.get("run_attempt") != int(attempt)):
        raise PromotionBlocked("CI provenance does not match the requested release")
    jobs = []
    page = 1
    while True:
        batch = api.github(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}")
        jobs.extend(batch["jobs"])
        if len(jobs) >= batch["total_count"]:
            break
        if not batch["jobs"] or page >= 20:
            raise PromotionBlocked("Incomplete CI job results")
        page += 1
    for name in REQUIRED_JOBS:
        matches = [job for job in jobs if job.get("name") == name]
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"):
            raise PromotionBlocked(f"Required CI job did not succeed: {name}")
    head = api.github(f"git/ref/heads/{quote(BRANCH, safe='')}")
    if head.get("object", {}).get("sha") != sha:
        raise PromotionBlocked("A newer branch commit exists; the older run cannot advance production")
    return sha


def approve(api, env):
    sha = validate_ci(api, env)
    # Confirm all automatic deployments will wait for the complete workflow.
    for role, service in SERVICES.items():
        data = api.railway("""query($project: String!, $environment: String!, $service: String!) {
          deploymentTriggers(projectId:$project, environmentId:$environment, serviceId:$service, first:10) {
            edges { node { branch repository checkSuites } }
          }
          variables(projectId:$project, environmentId:$environment, serviceId:$service)
        }""", {"project": PROJECT, "environment": ENVIRONMENT, "service": service})
        triggers = [edge["node"] for edge in data["deploymentTriggers"]["edges"]]
        if (len(triggers) != 1 or triggers[0].get("branch") != BRANCH
                or triggers[0].get("repository") != REPOSITORY
                or triggers[0].get("checkSuites") is not True):
            raise PromotionBlocked(f"{role}: source branch / Wait for CI configuration differs")
        require_paper_release_state(data.get("variables"), role)
    # Recheck after the remote reads and immediately before the sole pin mutation.
    if api.github(f"git/ref/heads/{quote(BRANCH, safe='')}").get("object", {}).get("sha") != sha:
        raise PromotionBlocked("Branch advanced during release approval")
    schema_head = repository_schema_head()
    patch = {"services": {service: {"variables": {
        "EXPECTED_RELEASE_COMMIT": {"value": sha},
        "EXPECTED_RELEASE_BRANCH": {"value": BRANCH},
        "EXPECTED_ALEMBIC_HEAD": {"value": schema_head},
    }} for service in SERVICES.values()}}
    for role, service in SERVICES.items():
        if role != "frontdoor":
            patch["services"][service]["deploy"] = {"preDeployCommand": [
                "python scripts/assert_release_source.py && "
                "python scripts/assert_database_schema.py --wait-seconds 600"
            ], "preDeployTimeoutSeconds": 900}
    # An explicit patch does not commit unrelated staged settings. Financial,
    # backup and storage evidence variables are deliberately absent.
    result = api.railway("""mutation($environment:String!, $patch:EnvironmentConfig!) {
      environmentPatchCommit(environmentId:$environment, patch:$patch, skipDeploys:true,
        commitMessage:"Approve exact CI-certified application source")
    }""", {"environment": ENVIRONMENT, "patch": patch})
    if not result.get("environmentPatchCommit"):
        raise PromotionBlocked("Railway did not confirm the release pin update")
    print(f"Approved application source {sha} for all four roles; financial settings unchanged.")
    # Explicit requests take new configuration snapshots, including the new pin.
    # Never redeploy an old deployment snapshot or resolve latestCommit at runtime.
    for role, service in SERVICES.items():
        result = api.railway("""mutation($environment:String!, $service:String!, $sha:String!) {
          serviceInstanceDeploy(environmentId:$environment, serviceId:$service,
            commitSha:$sha, latestCommit:false)
        }""", {"environment": ENVIRONMENT, "service": service, "sha": sha})
        if result.get("serviceInstanceDeploy") is not True:
            raise PromotionBlocked(f"{role}: deployment request was not accepted")
        print(f"Queued {role} at {sha}; deployment health is not yet verified.")
    return sha


def main():
    try:
        approve(APIs(), os.environ)
    except PromotionBlocked as exc:
        print(f"PRODUCTION_RELEASE_BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
