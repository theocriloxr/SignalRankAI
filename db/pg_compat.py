from __future__ import annotations

import asyncio
from typing import Any, Dict

from db.session import get_session
from db.session import get_database_url
from utils.async_runner import run_sync


def _run(coro):
    # Use run_sync shim which safely runs coroutines when an event loop
    # may already be active. This avoids RuntimeError in environments
    # where parts of the app already have a running loop.
    return run_sync(coro)


def postgres_enabled() -> bool:
    # Previously relied on a global ENGINE; use the session helper to
    # determine whether a DATABASE_URL is configured instead.
    return bool(get_database_url())


def get_all_user_ids_compat() -> list[int]:
    """Postgres-only. Returns all telegram user IDs."""
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured. Postgres is required.")

    async def _impl() -> list[int]:
        from db.pg_features import list_all_user_telegram_ids

        async with get_session() as session:
            ids = await list_all_user_telegram_ids(session)
            return ids

    return _run(_impl())


def store_signal_compat(signal: Dict[str, Any]) -> str:
    """Postgres-only. Store a signal and return its ID."""
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured. Postgres is required.")

    async def _impl() -> str:
        from db.pg_features import get_or_create_signal

        async with get_session() as session:
            s = await get_or_create_signal(session, signal)
            await session.commit()
            return s.signal_id

    return _run(_impl())
