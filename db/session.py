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

from config import config, resolve_database_url as _config_resolve_database_url, prefer_ipv4_database_url

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _engine_connect_args() -> dict[str, Any]:
    try:
        connect_timeout = float((os.getenv("DB_CONNECT_TIMEOUT") or "15").strip())
    except Exception:
        connect_timeout = 15.0
    try:
        command_timeout = float((os.getenv("DB_COMMAND_TIMEOUT") or "45").strip())
    except Exception:
        command_timeout = 45.0
    app_name = (os.getenv("DB_APP_NAME") or "signalrankai").strip() or "signalrankai"
    return {
        "timeout": connect_timeout,
        "command_timeout": command_timeout,
        "server_settings": {"application_name": app_name},
    }


def _prefer_ipv4_url(url: str) -> str:
    return prefer_ipv4_database_url(url)


def get_database_url() -> Optional[str]:
    url = _config_resolve_database_url(async_driver=True)
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


def _pool_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _is_railway_runtime() -> bool:
    railway_markers = (
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_REPLICA_ID",
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_PRIVATE_DOMAIN",
    )
    if any(bool((os.getenv(name) or "").strip()) for name in railway_markers):
        return True
    db_markers = (
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_PUBLIC_URL",
        "POSTGRES_URL",
        "POSTGRES_PRIVATE_URL",
    )
    return any("railway" in (os.getenv(name) or "").strip().lower() for name in db_markers)


def _effective_pool_settings() -> tuple[int, int]:
    pool_size = _pool_int("DB_POOL_SIZE", 5, minimum=1)
    max_overflow = _pool_int("DB_MAX_OVERFLOW", 3, minimum=0)

    # NullPool remains available for pgbouncer/transient debugging, but pooled
    # connections are the default so caps can be enforced explicitly.
    if _pool_bool("DB_USE_NULLPOOL", False):
        logger.info("[db] Using NullPool - connection pooling disabled for Railway compatibility")
        return 0, 0

    if _is_railway_runtime():
        disable_requested = _pool_bool("DB_POOL_DISABLE_RAILWAY_CAP", False)
        allow_uncapped = _pool_bool("DB_POOL_ALLOW_UNCAPPED_RAILWAY", False)
        if disable_requested and not allow_uncapped:
            logger.warning(
                "[db] DB_POOL_DISABLE_RAILWAY_CAP ignored on Railway; set "
                "DB_POOL_ALLOW_UNCAPPED_RAILWAY=1 only when Postgres max_connections is proven sufficient"
            )
        if disable_requested and allow_uncapped:
            logger.warning("[db] Railway DB pool cap disabled by explicit operator override")
            return pool_size, max_overflow

        railway_pool_cap = min(
            _pool_int("DB_POOL_SIZE_RAILWAY", 2, minimum=1),
            _pool_int("DB_POOL_RAILWAY_ABSOLUTE_CAP", 2, minimum=1),
        )
        railway_overflow_cap = min(
            _pool_int("DB_MAX_OVERFLOW_RAILWAY", 0, minimum=0),
            _pool_int("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP", 0, minimum=0),
        )
        original_pool_size = pool_size
        original_max_overflow = max_overflow
        pool_size = min(pool_size, railway_pool_cap)
        max_overflow = min(max_overflow, railway_overflow_cap)
        if (pool_size, max_overflow) != (original_pool_size, original_max_overflow):
            logger.warning(
                "[db] Railway pool cap applied requested_pool=%s requested_overflow=%s "
                "effective_pool=%s effective_overflow=%s",
                original_pool_size,
                original_max_overflow,
                pool_size,
                max_overflow,
            )
    else:
        global_pool_cap_raw = os.getenv("DB_POOL_GLOBAL_CAP")
        if global_pool_cap_raw:
            global_pool_cap = _pool_int("DB_POOL_GLOBAL_CAP", pool_size, minimum=1)
            pool_size = min(pool_size, global_pool_cap)
        global_overflow_cap_raw = os.getenv("DB_MAX_OVERFLOW_GLOBAL_CAP")
        if global_overflow_cap_raw:
            global_overflow_cap = _pool_int("DB_MAX_OVERFLOW_GLOBAL_CAP", max_overflow, minimum=0)
            max_overflow = min(max_overflow, global_overflow_cap)

    return pool_size, max_overflow


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url_or_none()
    if not url:
        return None
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
        pool_timeout=_pool_int("DB_POOL_TIMEOUT_SECONDS", 30, minimum=1),
        pool_recycle=_pool_int("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30),
        pool_pre_ping=_pool_bool("DB_POOL_PRE_PING", True),
        connect_args=_engine_connect_args(),
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engines_by_loop: dict[int, AsyncEngine] = {}
_sessionmakers_by_loop: dict[int, async_sessionmaker[AsyncSession]] = {}
_engine_lock = threading.Lock()
_sync_thread_local = threading.local()

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


def _normalize_database_url(raw: str, *, async_driver: bool) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return ""
    async_scheme = "postgresql+asyncpg://"
    sync_scheme = "postgresql+psycopg2://"
    if raw.startswith(async_scheme):
        return raw if async_driver else raw.replace(async_scheme, sync_scheme, 1)
    if raw.startswith(sync_scheme):
        return raw if not async_driver else raw.replace(sync_scheme, async_scheme, 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", async_scheme if async_driver else sync_scheme, 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", async_scheme if async_driver else sync_scheme, 1)
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
    auth = quote_plus(user) if not password else f"{quote_plus(user)}:{quote_plus(password)}"
    netloc = f"{auth}@{host}"
    if port:
        netloc = f"{netloc}:{port}"
    dsn = f"{scheme}://{netloc}/{quote_plus(database)}"
    sslmode = (os.getenv("PGSSLMODE") or os.getenv("DATABASE_SSLMODE") or os.getenv("DB_SSLMODE") or "").strip()
    if sslmode:
        dsn += f"?sslmode={quote_plus(sslmode)}"
    return dsn


def resolve_database_url(*, async_driver: bool = True) -> str:
    """Resolve DB URL for legacy callers, including PG* env var fallback."""
    configured = _config_resolve_database_url(async_driver=async_driver)
    if configured:
        return _normalize_database_url(configured, async_driver=async_driver)
    built = _build_pg_dsn_from_parts(async_driver=async_driver)
    return built or ""


def _create_engine_from_url(url: str) -> AsyncEngine:
    pool_size, max_overflow = _effective_pool_settings()
    if pool_size == 0 and max_overflow == 0:
        return create_async_engine(url, poolclass=NullPool, connect_args=_engine_connect_args())
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=_pool_int("DB_POOL_TIMEOUT_SECONDS", 30, minimum=1),
        pool_recycle=_pool_int("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30),
        pool_pre_ping=_pool_bool("DB_POOL_PRE_PING", True),
        connect_args=_engine_connect_args(),
    )


def get_sync_session():
    """Return a synchronous SQLAlchemy session for worker/maintenance paths."""
    from sqlalchemy import create_engine as create_sync_engine
    from sqlalchemy.orm import sessionmaker as sync_sessionmaker
    from sqlalchemy.pool import NullPool as SyncNullPool

    if not hasattr(_sync_thread_local, "sync_engine"):
        url = resolve_database_url(async_driver=False)
        if not url:
            raise RuntimeError("DATABASE_URL not configured")
        connect_args: dict[str, Any] = {}
        ssl_mode = os.getenv("PGSSLMODE", "prefer").lower()
        if ssl_mode == "require":
            connect_args["sslmode"] = "require"
        _sync_thread_local.sync_engine = create_sync_engine(
            url,
            poolclass=SyncNullPool,
            echo=_pool_bool("DB_ECHO", False),
            connect_args=connect_args,
        )
    Session = sync_sessionmaker(bind=_sync_thread_local.sync_engine, expire_on_commit=False)
    return Session()


async def init_db() -> None:
    """Create database tables from ORM metadata when an engine is configured."""
    engine = get_engine_for_event_loop()
    if engine is None:
        logger.warning("[db] Cannot init_db: engine not created")
        return
    from db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose all cached async engines and the thread-local sync engine."""
    global _global_engine
    with _engine_lock:
        engines = list(_engines_by_loop.values())
        _engines_by_loop.clear()
        _sessionmakers_by_loop.clear()
        _global_engine = None
    for engine in engines:
        try:
            await engine.dispose()
        except Exception as exc:
            logger.debug("[db] dispose failed: %s", exc)
    sync_engine = getattr(_sync_thread_local, "sync_engine", None)
    if sync_engine is not None:
        try:
            sync_engine.dispose()
        except Exception as exc:
            logger.debug("[db] sync dispose failed: %s", exc)
        try:
            delattr(_sync_thread_local, "sync_engine")
        except Exception:
            pass
