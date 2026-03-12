"""Database connection layer for SignalRankAI.

Postgres-only. All async engine and session logic lives in db/session.py.
This module re-exports the key helpers so any code that imports from
db.database continues to work without crashing the process.

The DATABASE_URL is read from the environment at connection time:
  1. DATABASE_PUBLIC_URL  (Railway external IPv4 proxy — preferred)
  2. DATABASE_URL         (standard env var)
Never hard-codes credentials or falls back to a local postgres user.
"""
from __future__ import annotations

from db.session import (
    get_session,
    get_database_url,
    create_engine,
    is_db_configured,
    get_engine_for_event_loop,
)

__all__ = [
    "get_session",
    "get_database_url",
    "create_engine",
    "is_db_configured",
    "get_engine_for_event_loop",
]

