#!/usr/bin/env python3
"""Fail-fast release source identity gate for Railway runtime roles."""
from __future__ import annotations

import os
import sys


def _value(name: str) -> str:
    return str(os.getenv(name) or "").strip().strip('"').strip("'")


def validate_release_source() -> list[str]:
    errors: list[str] = []
    railway = bool(_value("RAILWAY_SERVICE_NAME") or _value("RAILWAY_PROJECT_ID"))
    protected = railway or _value("SIGNALRANK_ENV_PROFILE") in {
        "staging-certification",
        "production-advisory",
        "production-live-owner-canary",
        "production",
    }
    if not protected:
        return errors

    expected_branch = _value("EXPECTED_RELEASE_BRANCH")
    actual_branch = _value("RAILWAY_GIT_BRANCH") or _value("GIT_BRANCH")
    if not expected_branch:
        errors.append("EXPECTED_RELEASE_BRANCH is missing")
    elif actual_branch != expected_branch:
        errors.append(f"runtime branch {actual_branch or 'unknown'} does not match {expected_branch}")

    expected_commit = _value("EXPECTED_RELEASE_COMMIT")
    actual_commit = _value("RAILWAY_GIT_COMMIT_SHA") or _value("GIT_COMMIT_SHA")
    if not expected_commit:
        errors.append("EXPECTED_RELEASE_COMMIT is missing")
    elif not actual_commit:
        errors.append("runtime commit is unavailable")
    elif actual_commit.lower() != expected_commit.lower():
        errors.append(
            f"runtime commit {actual_commit[:12]} does not match expected {expected_commit[:12]}"
        )
    return errors


def main() -> int:
    errors = validate_release_source()
    if errors:
        print("[release_source_gate] BLOCKED " + "; ".join(errors), file=sys.stderr)
        return 79
    print("[release_source_gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
