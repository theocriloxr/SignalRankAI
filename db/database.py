"""DEPRECATED: SQLite backend removed.

SignalRankAI is Postgres-only.

This module used to provide a SQLite-backed persistence layer. It is kept only
as a compatibility stub so that any accidental imports fail loudly and do not
silently fall back to demo/local data.
"""

from __future__ import annotations


raise RuntimeError(
    "SQLite support has been removed. Configure DATABASE_URL (Postgres) and use Postgres-backed modules."
)
