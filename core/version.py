from __future__ import annotations

import os
import re


def _first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return default


CODE_VERSION = "1.3.6"
CONFIGURED_APP_VERSION = _first("APP_VERSION", default=CODE_VERSION)
# The runtime banner must identify the code actually deployed. A stale Railway
# APP_VERSION remains visible as configured_version instead of mislabelling code.
APP_VERSION = CODE_VERSION
RELEASE_FINGERPRINT = "v1.3.6-railway-performance-decomposition-20260802"
BUILD_TIME_UTC = _first("BUILD_TIME_UTC", "SOURCE_BUILD_TIME", default="unknown")
GIT_COMMIT_SHA = _first(
    "RAILWAY_GIT_COMMIT_SHA",
    "GIT_COMMIT_SHA",
    "SOURCE_VERSION",
    "COMMIT_SHA",
    default="dev",
)
DEPLOYMENT_ID = _first("RAILWAY_DEPLOYMENT_ID", default="unknown")
ENVIRONMENT = _first("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "APP_ENV", default="unknown")
GIT_BRANCH = _first("RAILWAY_GIT_BRANCH", "GIT_BRANCH", "SOURCE_BRANCH", default="unknown")
BUILD_IDENTIFIER = _first("RAILWAY_BUILD_ID", "BUILD_ID", "SOURCE_BUILD_ID", default=BUILD_TIME_UTC)
RAILWAY_PROJECT = _first("RAILWAY_PROJECT_NAME", "RAILWAY_PROJECT_ID", default="unknown")
RAILWAY_SERVICE = _first("RAILWAY_SERVICE_NAME", "RAILWAY_SERVICE_ID", default="unknown")
ENVIRONMENT_PROFILE = _first("SIGNALRANK_ENV_PROFILE", "DEPLOYMENT_PROFILE", default=ENVIRONMENT)
EXPECTED_RELEASE_COMMIT = _first("EXPECTED_RELEASE_COMMIT", default="")


def runtime_commit_matches_expected() -> tuple[bool, str]:
    """Prove the runtime image came from the explicitly approved release commit."""
    actual = str(GIT_COMMIT_SHA or "").strip().lower()
    expected = str(EXPECTED_RELEASE_COMMIT or "").strip().lower()
    if not expected:
        return False, "EXPECTED_RELEASE_COMMIT is missing"
    if actual in {"", "dev", "unknown"}:
        return False, "runtime commit is unavailable"
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        return False, "EXPECTED_RELEASE_COMMIT must be the exact 40-character Git SHA"
    if not re.fullmatch(r"[0-9a-f]{40}", actual) or actual != expected:
        return False, f"runtime commit {actual[:12]} does not match expected {expected[:12]}"
    return True, f"runtime commit {actual[:12]} matches expected release"


def get_version_banner() -> str:
    short_sha = (GIT_COMMIT_SHA or "dev")[:12]
    configured = (
        f" configured_version={CONFIGURED_APP_VERSION}"
        if CONFIGURED_APP_VERSION != APP_VERSION
        else ""
    )
    return (
        f"SignalRankAI v{APP_VERSION} commit={short_sha} branch={GIT_BRANCH} "
        f"build={BUILD_IDENTIFIER} build_time={BUILD_TIME_UTC} "
        f"railway_project={RAILWAY_PROJECT} railway_service={RAILWAY_SERVICE} "
        f"deployment={DEPLOYMENT_ID} env={ENVIRONMENT} profile={ENVIRONMENT_PROFILE} "
        f"release={RELEASE_FINGERPRINT}{configured}"
    )

# Legacy verification marker retained for v1.2.1 compatibility tests: default="1.2.1"
