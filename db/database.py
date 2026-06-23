"""Database connection compatibility layer for SignalRankAI.

Postgres-only. Async engine/session lifecycle is owned by ``db.session``.
This module provides backward-compatible exports for legacy imports.

Resolution priority (via ``resolve_database_url`` from ``db.session``):
  1) PGBOUNCER_URL (if configured)
  2) DATABASE_URL / DATABASE_PRIVATE_URL / DATABASE_PUBLIC_URL / POSTGRES_URL / POSTGRESQL_URL
  3) PG* component synthesis
"""

from __future__ import annotations

from typing import Optional

from db.session import (
    get_engine_for_event_loop,
    get_session,
    is_db_configured,
    resolve_database_url,
)


def get_database_url() -> str:
    """Return resolved async database URL or raise if unavailable."""
    url = resolve_database_url(async_driver=True)
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def get_database_url_or_none() -> Optional[str]:
    """Return resolved async database URL if available, else None."""
    return resolve_database_url(async_driver=True)


def create_engine():
    """Backward-compatible accessor returning the shared async engine (or None)."""
    return get_engine_for_event_loop()


__all__ = [
    "get_session",
    "get_database_url",
    "get_database_url_or_none",
    "create_engine",
    "is_db_configured",
    "get_engine_for_event_loop",
]
