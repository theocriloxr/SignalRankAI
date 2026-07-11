"""Database connection layer for SignalRankAI.

Postgres-only. All async engine and session logic lives in db/session.py.
This module re-exports the key helpers so any code that imports from
db.database continues to work without crashing the process.

The DATABASE_URL is read from the environment at connection time:
  1. DATABASE_URL         (Railway internal/private URL when available)
  2. DATABASE_PRIVATE_URL (explicit private override, if provided)
  3. DATABASE_PUBLIC_URL  (external proxy fallback)
Never hard-codes credentials or falls back to a local postgres user.
"""
from __future__ import annotations

from db.session import (
    get_session,
    get_database_url as _session_get_database_url,
    get_database_url_or_none as _session_get_database_url_or_none,
    create_engine as _session_create_engine,
    is_db_configured,
    get_engine_for_event_loop,
)


def get_database_url():
    return _session_get_database_url()


def get_database_url_or_none():
    return _session_get_database_url_or_none()


def create_engine():
    return _session_create_engine()

__all__ = [
    "get_session",
    "get_database_url",
    "get_database_url_or_none",
    "create_engine",
    "is_db_configured",
    "get_engine_for_event_loop",
]
