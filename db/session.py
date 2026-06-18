from __future__ import annotations

import asyncio
import logging
import os
import random
import socket as _socket
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import config, resolve_database_url, prefer_ipv4_database_url

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _engine_connect_args() -> dict[str, Any]:
    # FIX: Increased default timeouts to prevent ML training timeouts on Railway
    try:
        connect_timeout = float((os.getenv("DB_CONNECT_TIMEOUT") or "60").strip())  # Increased from 15s to 60s
    except Exception:
        connect_timeout = 60.0  # Increased default for ML training
    try:
        command_timeout = float((os.getenv("DB_COMMAND_TIMEOUT") or "120").strip())  # Increased from 45s to 120s
    except Exception:
        command_timeout = 120.0  # Increased default for ML training
    app_name = (os.getenv("DB_APP_NAME") or "signalrankai").strip() or "signalrankai"
    return {
        "timeout": connect_timeout,
        "command_timeout": command_timeout,
        "server_settings": {"application_name": app_name},
    }


def _prefer_ipv4_url(url: str) -> str:
    return prefer_ipv4_database_url(url)


def get_database_url() -> Optional[str]:
    url = resolve_database_url(async_driver=True)
    if not url:
        raise ValueError(
            "DATABASE_URL is not set. Set DATABASE_URL (or DATABASE_PRIVATE_URL / DATABASE_PUBLIC_URL) "
            "as an environment variable."
        )
    return _prefer_ipv4_url(url)


def get_database_url_or_none() -> Optional[str]:
    try:
        return get_database_url()
    except ValueError:
        return None


def _pool_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int((os.getenv(name) or str(default)).strip()))
    except Exception:
        return default


def _pool_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _is_railway_runtime() -> bool:
    """Detect if running on Railway deployment."""
    return bool(
        (os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or 
        (os.getenv("RAILWAY_ENVIRONMENT") or "").strip() or
        (os.getenv("RAILWAY") or "").strip()
    )


def _effective_pool_settings() -> tuple[int, int]:
    # Force NullPool only when explicitly requested
    use_nullpool = os.getenv("DB_USE_NULLPOOL", "").strip().lower()
    if use_nullpool in ("1", "true", "yes", "on", "y"):
        logger.info("[db] Using NullPool - connection pooling disabled")
        return 0, 0

    # FIX: Check Railway environment - use smaller pool to avoid exhaustion
    # Railway hobby tier has ~20 connection limit, exceed causes "FATAL: too many clients"
    if _is_railway_runtime():
        # Railway: 5 + 2 = 7 total (safe for hobby tier)
        # Also enable pool_recycle and pool_pre_ping to prevent stale connections
        logger.info("[db] Railway runtime detected - using reduced pool (5+2=7)")
        return 5, 2

    # FIX: Increase pool size for concurrent operations
    # Default to 10 connections with 20 overflow for production workloads
    pool_size = _pool_int("DB_POOL_SIZE", 10, minimum=1)
    max_overflow = _pool_int("DB_MAX_OVERFLOW", 20, minimum=0)

    # Removed Railway-specific limit - hobby tier now supports 20 connections
    # If Railway needs smaller pool, they can set env vars explicitly

    return pool_size, max_overflow


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url_or_none()
    if not url:
        return None
    
    # FIX: Use _effective_pool_settings() for proper pool configuration
    # This returns pool_size=10, max_overflow=20 by default (or env var values)
    pool_size, max_overflow = _effective_pool_settings()
    
    # Use NullPool when pool_size is 0 (NullPool mode enabled)
    if pool_size == 0 and max_overflow == 0:
        return create_async_engine(
            url,
            poolclass=NullPool,
            connect_args=_engine_connect_args(),
        )
    
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args=_engine_connect_args(),
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engines_by_loop: dict[int, AsyncEngine] = {}
_sessionmakers_by_loop: dict[int, async_sessionmaker[AsyncSession]] = {}
_engine_lock = threading.Lock()

# Backward compatibility for legacy call-sites that still import
# `_get_global_engine` / `_global_engine` from this module.
_global_engine: Optional[AsyncEngine] = None


def _loop_identity() -> int:
    """Return a stable identity for the current async loop context.

    This prevents reusing an AsyncEngine across different event loops,
    which causes asyncpg queue/connection warnings and loop-bound errors.
    """
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        # Fallback for sync contexts that may call into async helpers.
        return -int(threading.get_ident())


def _get_engine_for_loop(loop_id: int) -> Optional[AsyncEngine]:
    if loop_id in _engines_by_loop:
        return _engines_by_loop[loop_id]
    with _engine_lock:
        if loop_id in _engines_by_loop:
            return _engines_by_loop[loop_id]
        try:
            url = get_database_url()
        except ValueError as exc:
            logger.critical("[db] DATABASE_URL is not configured: %s", exc)
            return None

        pool_size, max_overflow = _effective_pool_settings()

        # Use NullPool when pool_size is 0 (NullPool mode enabled)
        if pool_size == 0 and max_overflow == 0:
            engine = create_async_engine(
                url,
                poolclass=NullPool,
                connect_args=_engine_connect_args(),
            )
        else:
            engine = create_async_engine(
                url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=_pool_int("DB_POOL_TIMEOUT_SECONDS", 30, minimum=1),
                pool_recycle=_pool_int("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30),
                pool_pre_ping=_pool_bool("DB_POOL_PRE_PING", True),
                connect_args=_engine_connect_args(),
            )
        _engines_by_loop[loop_id] = engine
        _sessionmakers_by_loop[loop_id] = async_sessionmaker(engine, expire_on_commit=False)
        try:
            from sqlalchemy.engine.url import make_url as _mku

            _mu = _mku(url)
            _masked = f"{_mu.drivername}://{_mu.username}:***@{_mu.host}:{_mu.port}/{_mu.database}"
        except Exception:
            _masked = "<url parse error>"
        logger.info(
            "[db] async engine initialised loop=%s url=%s pool_size=%s max_overflow=%s",
            loop_id,
            _masked,
            pool_size,
            max_overflow,
        )
        return engine


def _get_sessionmaker_for_loop(loop_id: int) -> Optional[async_sessionmaker[AsyncSession]]:
    if loop_id in _sessionmakers_by_loop:
        return _sessionmakers_by_loop[loop_id]
    _get_engine_for_loop(loop_id)
    return _sessionmakers_by_loop.get(loop_id)


def get_engine_for_event_loop() -> Optional[AsyncEngine]:
    return _get_engine_for_loop(_loop_identity())


def _get_global_engine() -> Optional[AsyncEngine]:
    """Compatibility shim: return engine for current loop/thread context."""
    global _global_engine
    _global_engine = get_engine_for_event_loop()
    return _global_engine


def get_sessionmaker_for_event_loop() -> Optional[async_sessionmaker[AsyncSession]]:
    return _get_sessionmaker_for_loop(_loop_identity())


# Backward compatibility alias
async_session_maker = get_sessionmaker_for_event_loop


def is_db_configured() -> bool:
    return get_database_url_or_none() is not None


def is_transient_db_error(exc: BaseException) -> bool:
    txt = str(exc or "").lower()
    markers = (
        "toomanyconnectionserror",
        "too many clients already",
        "connection reset by peer",
        "server closed the connection unexpectedly",
        "terminating connection due to administrator command",
        "could not connect to server",
        "connection refused",
        "connection is closed",
    )
    return any(m in txt for m in markers)


async def run_with_db_retry(
    operation: Callable[[], Awaitable[_T]],
    *,
    retries: int | None = None,
    base_delay_s: float = 0.5,
    max_delay_s: float = 2.0,
    jitter_ratio: float = 0.10,
) -> _T:
    attempts = retries if retries is not None else _pool_int("DB_RETRY_ATTEMPTS", 3, minimum=0)
    attempts = max(0, int(attempts))
    attempt = 0
    while True:
        try:
            return await operation()
        except Exception as exc:
            if attempt >= attempts or (not is_transient_db_error(exc)):
                raise
            delay = min(max_delay_s, base_delay_s * (2**attempt))
            jitter = delay * max(0.0, jitter_ratio) * random.random()
            wait_for = delay + jitter
            logger.warning(
                "[db] transient failure retry=%s/%s wait_s=%.2f err=%s",
                attempt + 1,
                attempts,
                wait_for,
                exc,
            )
            await asyncio.sleep(wait_for)
            attempt += 1


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    session_local = _get_sessionmaker_for_loop(_loop_identity())
    if session_local is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with session_local() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


# =============================================================================
# SYNCHRONOUS SESSION FIX for asyncpg thread deadlock
# When ML training runs in a separate thread (asyncio.to_thread()),
# async sessions cannot cross thread boundaries.
# Use synchronous SQLAlchemy for thread-safe background tasks.
# =============================================================================

def _create_sync_engine() -> Optional[Any]:
    """Create a synchronous SQLAlchemy engine for background tasks."""
    url = get_database_url_or_none()
    if not url:
        return None

    # Convert from async driver to sync driver
    # postgresql+asyncpg:// -> postgresql://
    sync_url = url.replace("+asyncpg", "")

    from sqlalchemy import create_engine

    return create_engine(
        sync_url,
        pool_size=_pool_int("DB_SYNC_POOL_SIZE", 10, minimum=1),
        max_overflow=_pool_int("DB_SYNC_MAX_OVERFLOW", 10, minimum=0),
        pool_timeout=_pool_int("DB_SYNC_POOL_TIMEOUT_SECONDS", 60, minimum=1),
        pool_recycle=_pool_int("DB_SYNC_POOL_RECYCLE_SECONDS", 1800, minimum=30),
        pool_pre_ping=_pool_bool("DB_SYNC_POOL_PRE_PING", True),
    )


_sync_engine = None
_sync_sessionmaker = None


def get_sync_session():
    """Get a synchronous session factory for background tasks.

    This creates a separate synchronous connection pool that can be used
    safely in background threads where the async event loop is not available.

    Usage:
        from db.session import get_sync_session
        Session = get_sync_session()
        with Session() as session:
            # synchronous queries
            result = session.query(Model).all()
    """
    global _sync_engine, _sync_sessionmaker

    if _sync_engine is None:
        _sync_engine = _create_sync_engine()
        if _sync_engine is None:
            raise RuntimeError("DATABASE_URL is not configured")

    if _sync_sessionmaker is None:
        from sqlalchemy.orm import sessionmaker

        _sync_sessionmaker = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_sync_engine
        )

    return _sync_sessionmaker
