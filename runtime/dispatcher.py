"""Process dispatcher for canonical runtime roles.

Dispatch is deliberately a thin lazy-import table. It does not perform
migrations, create database pools, or start background work while imported.
The optional ``legacy_worker`` switch keeps the existing ``RUN_MODE=worker``
deployment behavior during the delivery-worker migration.
"""

from __future__ import annotations

from typing import Any

from runtime.roles import RunMode, parse_run_mode


def dispatch(mode: str | RunMode | None, *, legacy_worker: bool = False) -> Any:
    """Start one role and return its adapter result."""

    raw = str(mode or "").strip().lower()
    parsed = parse_run_mode(mode)
    if parsed is RunMode.WEB:
        from runtime.web import run
    elif parsed is RunMode.BOT:
        from runtime.bot import run
    elif parsed is RunMode.ENGINE:
        from runtime.engine import run
    elif parsed is RunMode.DELIVERY:
        if legacy_worker and raw == "worker":
            from worker.worker import main as run
        else:
            from runtime.delivery import run
    elif parsed is RunMode.OUTCOME:
        from runtime.outcome import run
    elif parsed is RunMode.ANALYTICS:
        from runtime.analytics import run
    elif parsed is RunMode.SCHEDULER:
        from runtime.scheduler import run
    elif parsed is RunMode.ALL_DEV:
        from runtime.all_dev import run
    else:  # pragma: no cover - parse_run_mode is exhaustive
        raise ValueError(f"No dispatcher registered for {parsed!r}")
    return run()


__all__ = ["dispatch"]
