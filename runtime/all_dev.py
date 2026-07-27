"""Local all-in-one compatibility role.

The existing ``railway_main`` lifespan remains the proven composition while
role-specific services are migrated one ownership boundary at a time.
"""

from __future__ import annotations

import os


def run() -> None:
    import uvicorn

    uvicorn.run(
        "railway_main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
    )


start = run

__all__ = ["run", "start"]
