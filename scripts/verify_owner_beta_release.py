"""One-command offline release verification for the owner-only Railway beta.

The verifier deliberately avoids live provider calls and never prints secrets.
It combines the launch-critical source, schema, governance, environment, and
regression checks that should pass before each Railway deployment.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]


def _python(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


def build_checks(*, include_tests: bool = True) -> list[Check]:
    env_profiles = [
        "RAILWAY_24H_SOAK_NO_SECRETS.env",
        "configs/env/production.env.example",
        "configs/env/railway-staging.env.example",
        "deploy/railway_roles/gateway.env",
        "deploy/railway_roles/engine.env",
        "deploy/railway_roles/worker.env",
        "deploy/railway_roles/outcome.env",
        "deploy/railway_roles/delivery.env",
        "deploy/railway_roles/analytics.env",
        "deploy/railway_roles/monolith_safe.env",
    ]
    checks = [
        Check("compile", _python("-m", "compileall", "-q", ".")),
        Check("schema", _python("scripts/schema_audit.py")),
        Check("db-session-api", _python("scripts/audit_db_session_calls.py")),
        Check("architecture", _python("scripts/architecture_smoke.py")),
        Check("governance", _python("scripts/validate_governance_docs.py")),
        Check("secret-scan", _python("scripts/secret_scan.py")),
        Check("readiness", _python("scripts/production_readiness_check.py")),
        Check(
            "environment-contracts",
            _python("scripts/validate_env_contract.py", *env_profiles),
        ),
    ]
    if include_tests:
        checks.append(
            Check(
                "production-regressions",
                _python(
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_runtime_hotfix_20260725.py",
                    "tests/test_production_endgame_20260725.py",
                    "tests/test_phase4_pass7_runtime_roles.py",
                ),
            )
        )
    return checks


def _run(check: Check, *, env: dict[str, str]) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    result = subprocess.run(
        check.command,
        cwd=ROOT,
        env=env,
        text=True,
        check=False,
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {check.name}", flush=True)
    return result.returncode == 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Run source/audit checks only when pytest dependencies are unavailable.",
    )
    args = parser.parse_args(argv)

    env = dict(os.environ)
    env.setdefault("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1")
    env.setdefault("ASSET_UNIVERSE_BACKGROUND_REFRESH_ENABLED", "0")
    env.setdefault("PUBLIC_TESTING_MODE", "0")
    env.setdefault("ML_OFFLINE_BOOTSTRAP_ENABLED", "0")

    failures: list[str] = []
    for check in build_checks(include_tests=not args.skip_tests):
        if not _run(check, env=env):
            failures.append(check.name)

    print("\n=== release summary ===")
    if failures:
        print("BLOCKED: " + ", ".join(failures))
        return 1
    print("PASS: owner-beta offline release checks are clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
