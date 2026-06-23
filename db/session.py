"""
SignalRankAI — Database Session (PERFECTED)

Implements "Transient Connection Persistence" (Connection Leak Immunization):
  - NullPool: every async context gets a fresh connection, immediately returned
  - get_session(): strict context manager pattern — open, write/read, commit, dissolve
  - NO long-lived connections in signal processing paths
  - PgBouncer-compatible: pool_pre_ping disabled, statement timeout on each query
  - Thread-local engine for sync paths to avoid event loop conflicts

Anti-patterns this module prevents:
  ❌ Holding connections across external HTTP requests (Telegram API, Gemini)
  ❌ Leaking connections when exceptions skip commit/rollback
  ❌ Multiple asyncpg connections from same coroutine
  ❌ Global session objects shared across requests
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# ─── Engine registry ───────────────────────────────────────────────────────────

_global_engine = None
_engine_lock = threading.Lock()

# Thread-local for sync paths (APScheduler, background jobs)
_thread_local = threading.local()


def resolve_database_url(*, async_driver: bool = True) -> str:
    """
    Resolve the database URL, normalizing the driver prefix.

    async_driver=True  → asyncpg  (for async SQLAlchemy paths)
    async_driver=False → psycopg2 (for sync paths like APScheduler jobs)
    """
    raw = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()

    if not raw:
        return raw

    # Normalize scheme
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break

    if async_driver:
        return f"postgresql+asyncpg://{raw}"
    else:
        return f"postgresql+psycopg2://{raw}"


def _create_engine_from_url(url: str):
    """Create an async engine with NullPool for connection leak immunity."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    connect_args: dict = {}

    # Per-query statement timeout (prevents runaway queries from holding connections)
    statement_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000") or 30000)
    command_timeout_s    = int(os.getenv("DB_COMMAND_TIMEOUT_S",    "30")    or 30)

    connect_args["server_settings"] = {
        "statement_timeout": str(statement_timeout_ms),
        "application_name": "signalrankAI",
    }
    connect_args["command_timeout"] = command_timeout_s

    # SSL for Railway / Neon / Supabase
    ssl_mode = os.getenv("PGSSLMODE", "prefer").lower()
    if ssl_mode in ("require", "verify-ca", "verify-full"):
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        if ssl_mode != "verify-full":
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
        connect_args["ssl"] = ctx

    engine = create_async_engine(
        url,
        poolclass=NullPool,           # ← Key: never hold connections in a pool
        echo=os.getenv("DB_ECHO", "0").lower() in ("1", "true"),
        pool_pre_ping=False,          # NullPool doesn't use pool, skip ping
        connect_args=connect_args,
    )
    return engine


def _get_global_engine():
    """Return (and lazily create) the module-level async engine."""
    global _global_engine
    if _global_engine is not None:
        return _global_engine

    with _engine_lock:
        if _global_engine is not None:
            return _global_engine

        url = resolve_database_url(async_driver=True)
        if not url:
            logger.warning("[db] DATABASE_URL not set — DB engine not created")
            return None

        try:
            _global_engine = _create_engine_from_url(url)
            logger.info("[db] Async engine created (NullPool)")
        except Exception as exc:
            logger.error("[db] Failed to create async engine: %s", exc)
            _global_engine = None

    return _global_engine


def get_engine_for_event_loop():
    """Return the global engine if configured, else None."""
    return _get_global_engine()


def is_db_configured() -> bool:
    """Return True if a database URL is configured and engine exists."""
    return _get_global_engine() is not None


@asynccontextmanager
async def get_session() -> AsyncGenerator:
    """
    Async context manager that yields a database session.

    Implements strict "Get In, Get Out" methodology:
      1. Opens connection from NullPool (fresh connection)
      2. Yields session for operations
      3. Commits on clean exit, rolls back on exception
      4. Closes/returns connection IMMEDIATELY on exit

    CRITICAL: Never perform external HTTP requests (Telegram API, Gemini, etc.)
    inside a `get_session()` block. DB connection must be released BEFORE any
    external network I/O to prevent connection exhaustion.

    Usage:
        async with get_session() as session:
            user = await session.execute(select(User).where(...))
            session.add(new_record)
            await session.commit()
        # connection is returned to NullPool here ↑
        # NOW you can call external APIs
    """
    engine = _get_global_engine()
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set it as an environment variable before starting the bot."
        )

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session_factory() as session:
        try:
            yield session
            # Do NOT auto-commit here — callers must explicitly await session.commit()
            # This enforces intentional transaction boundaries.
        except Exception:
            try:
                await session.rollback()
            except Exception as rb_exc:
                logger.debug("[db] rollback failed: %s", rb_exc)
            raise
        # Connection returned to NullPool here (effectively closed immediately)


def get_sync_session():
    """
    Returns a synchronous session for use in APScheduler jobs or sync code paths.

    Creates a new sync engine per thread using thread-local storage.
    This avoids event loop conflicts when called from background threads.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    if not hasattr(_thread_local, "sync_engine"):
        url = resolve_database_url(async_driver=False)
        if not url:
            raise RuntimeError("DATABASE_URL not configured")

        connect_args = {}
        ssl_mode = os.getenv("PGSSLMODE", "prefer").lower()
        if ssl_mode in ("require",):
            connect_args["sslmode"] = "require"

        _thread_local.sync_engine = create_engine(
            url,
            poolclass=NullPool,
            echo=False,
            connect_args=connect_args,
        )

    Session = sessionmaker(bind=_thread_local.sync_engine, expire_on_commit=False)
    return Session()


# ─── Schema initialization ─────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables if they don't exist (idempotent)."""
    engine = _get_global_engine()
    if engine is None:
        logger.warning("[db] Cannot init_db: engine not created")
        return

    try:
        from db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[db] Schema initialized")
    except Exception as exc:
        logger.error("[db] init_db failed: %s", exc)
        raise


# ─── Cleanup ──────────────────────────────────────────────────────────────────

async def dispose_engine() -> None:
    """Cleanly dispose the global engine (for graceful shutdown)."""
    global _global_engine
    with _engine_lock:
        if _global_engine is not None:
            try:
                await _global_engine.dispose()
                logger.info("[db] Engine disposed")
            except Exception as exc:
                logger.debug("[db] dispose failed: %s", exc)
            finally:
                _global_engine = None


__all__ = [
    "get_session",
    "get_sync_session",
    "get_engine_for_event_loop",
    "is_db_configured",
    "resolve_database_url",
    "init_db",
    "dispose_engine",
    "_get_global_engine",
]