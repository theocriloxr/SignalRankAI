"""Local-only Railway simulation entrypoint.

Production imports ``railway_main:app`` directly. The simulator may install the
same pytest-only optional dependency stubs when the execution environment is
offline and cannot install declared runtime dependencies.
"""
from __future__ import annotations

import os

if str(os.getenv("SIGNALRANK_SIMULATION_OPTIONAL_STUBS", "0")).lower() in {"1", "true", "yes", "on"}:
    from tests._dependency_stubs import install_optional_dependency_stubs

    install_optional_dependency_stubs()

from railway_main import app  # noqa: E402

__all__ = ["app"]
