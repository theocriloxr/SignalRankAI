"""Fast HTTP/Telegram front-door role for decomposed Railway deployments."""
from __future__ import annotations

import os


def run() -> None:
    import uvicorn

    # Fail closed: this adapter must never embed engine/worker loops.
    os.environ["RUN_MODE"] = "frontdoor"
    os.environ.setdefault("DECOMPOSED_TOPOLOGY_ENABLED", "1")
    os.environ["RUN_ENGINE_LOOP"] = "0"
    os.environ["RUN_WORKER_LOOP"] = "0"
    uvicorn.run(
        "railway_main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
    )


start = run
__all__ = ["run", "start"]
