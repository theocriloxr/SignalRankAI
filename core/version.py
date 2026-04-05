from __future__ import annotations

import os


APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
BUILD_TIME_UTC = os.getenv("BUILD_TIME_UTC", "unknown")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "dev")


def get_version_banner() -> str:
    short_sha = (GIT_COMMIT_SHA or "dev")[:7]
    return f"SignalRankAI v{APP_VERSION} ({short_sha}) build={BUILD_TIME_UTC}"
