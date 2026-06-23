"""
SignalRankAI — Database Session (Hardened)

Implements transient connection lifecycle:
  - NullPool: each DB interaction gets a fresh connection and returns immediately
  - Strict async context manager usage for sessions
  - Thread-local sync engine for non-async worker paths
  - Defensive logging and compatibility helper exports
"""

from __future__ import annotations

import logging
import os
import threading
import traceback
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

_global_engine: Optional[AsyncEngine] = None
_engine_lock = threading.Lock()
_thread_local = threading.local()


def _normalize_database_url(raw: str, *, async_driver: bool) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return ""

    if raw.startswith("postgresql+asyncpg://"):
        return raw if async_driver else raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if raw.startswith("postgresql+psycopg2://"):
        return raw if not async_driver else raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://" if async_driver else "postgresql+psycopg2://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://" if async_driver else "postgresql+psycopg2://", 1)

    return raw


def _build_pg_dsn_from_parts(*, async_driver: bool) -> Optional[str]:
    host = (os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or os.getenv("DATABASE_HOST") or "").strip()
    user = (os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or os.getenv("DATABASE_USER") or "").strip()
    password = (os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or os.getenv("DATABASE_PASSWORD") or "").strip()
    database = (os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or os.getenv("DATABASE_NAME") or "").strip()
    port = (os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or os.getenv("DATABASE_PORT") or "").strip()

    if not host or not user or not database:
        return None

    from urllib.parse import quote_plus

    scheme = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
    user_enc = quote_plus(user)
    auth = user_enc if not password else f"{user_enc}:{quote_plus(password)}"
    netloc = f"{auth}@{host}"
    if port:
        netloc = f"{netloc}:{port}"

    dsn = f"{scheme}://{netloc}/{database}"
    sslmode = (os.getenv("PGSSLMODE") or os.getenv("DATABASE_SSLMODE") or os.getenv("DB_SSLMODE") or "").strip()
    if sslmode:
        sep = "&" if "?" in dsn else "?"
        dsn = f"{dsn}{sep}sslmode={quote_plus(sslmode)}"
    return dsn


def resolve_database_url(*, async_driver: bool = True) -> str:
    """
    Resolve database URL with deterministic priority:
      1) PGBOUNCER_URL
      2) DATABASE_URL / DATABASE_PRIVATE_URL / DATABASE_PUBLIC_URL / POSTGRES_URL / POSTGRESQL_URL
      3) DSN synthesized from PG* environment variables
    """
    candidates: list[str] = []

    pgbouncer = (os.getenv("PGBOUNCER_URL") or "").strip()
    if pgbouncer:
        candidates.append(pgbouncer)

    for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "DATABASE_PUBLIC_URL", "POSTGRES_URL", "POSTGRESQL_URL"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            candidates.append(raw)

    built = _build_pg_dsn_from_parts(async_driver=async_driver)
    if built:
        candidates.append(built)

    for raw in candidates:
        normalized = _normalize_database_url(raw, async_driver=async_driver)
        if normalized:
            return normalized

    return ""


def _create_engine_from_url(url: str) -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    connect_args: dict[str, Any] = {}

    statement_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000") or 30000)
    command_timeout_s = int(os.getenv("DB_COMMAND_TIMEOUT_S", "30") or 30)

    connect_args["server_settings"] = {
        "statement_timeout": str(statement_timeout_ms),
        "application_name": "signalrankAI",
    }
    connect_args["command_timeout"] = command_timeout_s

    ssl_mode = os.getenv("PGSSLMODE", "prefer").lower()
    if ssl_mode in ("require", "verify-ca", "verify-full"):
        import ssl as _ssl

        ctx = _ssl.create_default_context()
        if ssl_mode != "verify-full":
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
        connect_args["ssl"] = ctx

    return create_async_engine(
        url,
        poolclass=NullPool,
        echo=os.getenv("DB_ECHO", "0").lower() in ("1", "true"),
        pool_pre_ping=False,
        connect_args=connect_args,
    )


def _get_global_engine() -> Optional[AsyncEngine]:
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
        except Exception:
            logger.error("[db] Failed to create async engine: %s", traceback.format_exc())
            _global_engine = None

    return _global_engine


def get_engine_for_event_loop() -> Optional[AsyncEngine]:
    return _get_global_engine()


def is_db_configured() -> bool:
    return bool(resolve_database_url(async_driver=True))


def get_database_url() -> str:
    url = resolve_database_url(async_driver=True)
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def get_database_url_or_none() -> Optional[str]:
    url = resolve_database_url(async_driver=True)
    return url or None


def create_engine() -> Optional[AsyncEngine]:
    return get_engine_for_event_loop()


def is_transient_db_error(exc: BaseException) -> bool:
    """
    Backward-compatible transient DB error classifier used by db.pg_features.

    Returns True for temporary/transport-level database errors that are
    typically safe to retry.
    """
    try:
        msg = f"{type(exc).__name__}: {exc}".lower()
    except Exception:
        msg = ""

    transient_markers = (
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "connection aborted",
        "could not connect",
        "too many clients",
        "deadlock",
        "serialization",
        "transient",
        "temporarily unavailable",
        "server closed the connection",
        "connection is closed",
    )
    return any(marker in msg for marker in transient_markers)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = _get_global_engine()
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it as an environment variable before starting the bot."
        )

    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            try:
                await session.rollback()
            except Exception:
                logger.debug("[db] rollback failed: %s", traceback.format_exc())
            raise


def get_sync_session():
    from sqlalchemy import create_engine as create_sync_engine
    from sqlalchemy.orm import sessionmaker as sync_sessionmaker
    from sqlalchemy.pool import NullPool

    if not hasattr(_thread_local, "sync_engine"):
        url = resolve_database_url(async_driver=False)
        if not url:
            raise RuntimeError("DATABASE_URL not configured")

        connect_args = {}
        ssl_mode = os.getenv("PGSSLMODE", "prefer").lower()
        if ssl_mode in ("require",):
            connect_args["sslmode"] = "require"

        _thread_local.sync_engine = create_sync_engine(
            url,
            poolclass=NullPool,
            echo=False,
            connect_args=connect_args,
        )

    Session = sync_sessionmaker(bind=_thread_local.sync_engine, expire_on_commit=False)
    return Session()


async def init_db() -> None:
    engine = _get_global_engine()
    if engine is None:
        logger.warning("[db] Cannot init_db: engine not created")
        return

    try:
        from db.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[db] Schema initialized")
    except Exception:
        logger.error("[db] init_db failed: %s", traceback.format_exc())
        raise


async def dispose_engine() -> None:
    global _global_engine
    with _engine_lock:
        if _global_engine is not None:
            try:
                await _global_engine.dispose()
                logger.info("[db] Engine disposed")
            except Exception:
                logger.debug("[db] dispose failed: %s", traceback.format_exc())
            finally:
                _global_engine = None


__all__ = [
    "get_session",
    "get_sync_session",
    "get_engine_for_event_loop",
    "is_db_configured",
    "resolve_database_url",
    "get_database_url",
    "get_database_url_or_none",
    "create_engine",
    "init_db",
    "dispose_engine",
    "_get_global_engine",
    "is_transient_db_error",
]
