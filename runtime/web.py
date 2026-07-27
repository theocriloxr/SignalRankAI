"""Web role adapter.

The canonical FastAPI application is loaded lazily so importing the role
contract does not create database clients or application state.
"""

from __future__ import annotations

import os
from typing import Any


def create_app() -> Any:
    from web.app import app

    return app


def run() -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
    )


start = run

__all__ = ["create_app", "run", "start"]
