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

from config import config, resolve_database_url, prefer_ipv4_database_url

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


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url_or_none()
    if not url:
        return None
    return create_async_engine(
        url,
        pool_size=_pool_int("DB_POOL_SIZE", 15, minimum=1),
        max_overflow=_pool_int("DB_MAX_OVERFLOW", 5, minimum=0),
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

        engine = create_async_engine(
            url,
            pool_size=_pool_int("DB_POOL_SIZE", 15, minimum=1),
            max_overflow=_pool_int("DB_MAX_OVERFLOW", 5, minimum=0),
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
            _pool_int("DB_POOL_SIZE", 15, minimum=1),
            _pool_int("DB_MAX_OVERFLOW", 5, minimum=0),
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
