from __future__ import annotations

import asyncio
from typing import Any, Dict

from db.session import ENGINE, get_session


def _run(coro):
    try:
        asyncio.get_running_loop()
        # In an active loop, caller should await instead.
        raise RuntimeError("Cannot run sync Postgres helper inside running event loop")
    except RuntimeError as e:
        if str(e).startswith("Cannot run sync"):
            raise
    return asyncio.run(coro)


def postgres_enabled() -> bool:
    return ENGINE is not None


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
