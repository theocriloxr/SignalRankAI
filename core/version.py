from __future__ import annotations

import os


def _first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return default


APP_VERSION = _first("APP_VERSION", default="1.2.1")
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


def get_version_banner() -> str:
    short_sha = (GIT_COMMIT_SHA or "dev")[:12]
    return (
        f"SignalRankAI v{APP_VERSION} commit={short_sha} "
        f"build={BUILD_TIME_UTC} deployment={DEPLOYMENT_ID} env={ENVIRONMENT}"
    )
