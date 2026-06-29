from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from db.session import get_session
from db.session import get_database_url_or_none
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)


def _run(coro):
    # Use run_sync shim which safely runs coroutines when an event loop
    # may already be active. This avoids RuntimeError in environments
    # where parts of the app already have a running loop.
    return run_sync(coro)


def postgres_enabled() -> bool:
    # Use get_database_url_or_none() so that a missing DATABASE_URL returns
    # False (safe) instead of raising ValueError (which propagates through
    # bool() and crashes the caller).
    return bool(get_database_url_or_none())


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
        from db.pg_features import SignalDedupBlocked, get_or_create_signal
        import os

        dedup_hours = signal.get("dedup_hours", signal.get("_dedup_hours"))
        if dedup_hours is None:
            try:
                dedup_hours = int((os.getenv("SIGNAL_DEDUP_HOURS") or "24").strip())
            except Exception:
                dedup_hours = 24
        else:
            try:
                dedup_hours = int(dedup_hours)
            except Exception:
                dedup_hours = 24

        async with get_session() as session:
            try:
                s = await get_or_create_signal(session, signal, dedup_hours=dedup_hours)
            except SignalDedupBlocked as exc:
                logger.warning(
                    "[store_signal] blocked reason=%s asset=%s timeframe=%s direction=%s signal_id=%s",
                    getattr(exc, "reason", str(exc)),
                    signal.get("asset") or signal.get("symbol"),
                    signal.get("timeframe"),
                    signal.get("direction"),
                    getattr(exc, "signal_id", None),
                )
                return str(exc.signal_id or "")
            await session.commit()
            return s.signal_id

    return _run(_impl())
