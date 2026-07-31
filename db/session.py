from __future__ import annotations

import asyncio
import logging
import inspect
import os
import random
import re
import socket as _socket
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import config, resolve_database_url as _config_resolve_database_url, prefer_ipv4_database_url
from db.priority import DBAdmissionController, DBPriority

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _database_role() -> str:
    raw = (
        os.getenv("DB_ROLE")
        or os.getenv("RUN_MODE")
        or os.getenv("RAILWAY_SERVICE_NAME")
        or "app"
    )
    role = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(raw).strip().lower()).strip("-.")
    return (role or "app")[:48]


def _is_decomposed_database_role() -> bool:
    """Only dedicated non-monolith services may use reviewed larger pools."""
    return _database_role() in {
        "analytics",
        "bot",
        "delivery",
        "engine",
        "outcome",
        "scheduler",
        "worker",
    }


def _database_application_name() -> str:
    explicit = (os.getenv("DB_APP_NAME") or "").strip()
    return explicit or f"signalrankai/{_database_role()}"


def _engine_connect_args() -> dict[str, Any]:
    try:
        connect_timeout = float((os.getenv("DB_CONNECT_TIMEOUT") or "15").strip())
    except Exception:
        connect_timeout = 15.0
    try:
        command_timeout = float((os.getenv("DB_COMMAND_TIMEOUT") or "45").strip())
    except Exception:
        command_timeout = 45.0
    app_name = _database_application_name()
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


def _pool_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(float(minimum), float((os.getenv(name) or str(default)).strip()))
    except Exception:
        return float(default)


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
    max_overflow = _pool_int("DB_MAX_OVERFLOW", 2, minimum=0)

    # NullPool remains available for pgbouncer/transient debugging, but pooled
    # connections are the default so caps can be enforced explicitly.
    if _pool_bool("DB_USE_NULLPOOL", False):
        logger.info("[db] Using NullPool - connection pooling disabled for Railway compatibility")
        return 0, 0

    if _is_railway_runtime():
        # PUBLIC_TESTING_MODE blocks any attempt to disable the Railway pool cap.
        # The override env vars are completely ignored in public-testing mode.
        _public_testing = _pool_bool("PUBLIC_TESTING_MODE", False)
        
        # Check for unsafe overrides and log them as errors (not warnings) so
        # operators know the override was ignored.
        disable_requested = _pool_bool("DB_POOL_DISABLE_RAILWAY_CAP", False)
        allow_uncapped = _pool_bool("DB_POOL_ALLOW_UNCAPPED_RAILWAY", False)
        
        if disable_requested or allow_uncapped:
            if _public_testing:
                logger.warning(
                    "[db_pool_safe] Railway pool override BLOCKED by PUBLIC_TESTING_MODE; "
                    "DB_POOL_DISABLE_RAILWAY_CAP and DB_POOL_ALLOW_UNCAPPED_RAILWAY are ignored"
                )
            else:
                logger.warning(
                    "[db] Railway DB pool cap overrides detected but not applied; "
                    "set PUBLIC_TESTING_MODE=0 and both flags only if Postgres max_connections is proven sufficient"
                )

        # Fail-safe monolith limits. A stale Railway variable such as
        # DB_POOL_SIZE=200 or DB_POOL_SIZE_RAILWAY=20 must not reserve a large
        # pool. The conservative defaults remain 2/0.
        # An explicit DB_POOL_RAILWAY_ABSOLUTE_CAP is valid only for a dedicated
        # decomposed service. The monolith creates auxiliary event-loop engines
        # and must remain at 2/0 even when stale soak-test variables survive.
        absolute_pool_raw = os.getenv("DB_POOL_RAILWAY_ABSOLUTE_CAP")
        absolute_overflow_raw = os.getenv("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP")
        decomposed_role = _is_decomposed_database_role()
        
        # In public-testing mode, enforce strictest defaults regardless of overrides.
        if _public_testing:
            railway_pool_cap = 2
            railway_overflow_cap = 0
            logger.info(
                "[db_pool_safe] PUBLIC_TESTING_MODE enabled: forced pool_size=%s max_overflow=%s",
                railway_pool_cap,
                railway_overflow_cap,
            )
        elif absolute_pool_raw is not None and decomposed_role:
            railway_pool_cap = _pool_int("DB_POOL_RAILWAY_ABSOLUTE_CAP", 2, minimum=1)
        else:
            railway_pool_cap = min(_pool_int("DB_POOL_SIZE_RAILWAY", 2, minimum=1), 2)
        
        if _public_testing:
            railway_overflow_cap = 0
        elif absolute_overflow_raw is not None and decomposed_role:
            railway_overflow_cap = _pool_int("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP", 0, minimum=0)
        else:
            railway_overflow_cap = min(_pool_int("DB_MAX_OVERFLOW_RAILWAY", 0, minimum=0), 0)

        if not decomposed_role and (
            (absolute_pool_raw is not None and _pool_int("DB_POOL_RAILWAY_ABSOLUTE_CAP", 2, minimum=1) > 2)
            or (
                absolute_overflow_raw is not None
                and _pool_int("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP", 0, minimum=0) > 0
            )
        ):
            logger.warning(
                "[db_pool_safe] ignored oversized Railway absolute pool cap for monolith role=%s; "
                "effective maximum is DB_POOL_SIZE=2 DB_MAX_OVERFLOW=0",
                _database_role(),
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


def _default_session_gate_limit() -> int:
    pool_size, max_overflow = _effective_pool_settings()
    if pool_size == 0 and max_overflow == 0:
        return _pool_int("DB_NULLPOOL_SESSION_GATE_DEFAULT", 8, minimum=1)
    configured_capacity = max(1, int(pool_size or 0) + int(max_overflow or 0))
    default_cap = _pool_int("DB_SESSION_GATE_DEFAULT_CAP", 40, minimum=1)
    return max(1, min(configured_capacity, default_cap))


def _effective_session_gate_limit() -> int:
    requested = max(
        1,
        _pool_int(
            "DB_MAX_CONCURRENT_SESSIONS",
            _default_session_gate_limit(),
            minimum=1,
        ),
    )
    pool_size, max_overflow = _effective_pool_settings()
    if pool_size == 0 and max_overflow == 0:
        return requested
    physical_capacity = max(1, int(pool_size) + int(max_overflow))
    effective = min(requested, physical_capacity)
    if effective != requested:
        logger.warning(
            "[db] session gate capped to physical pool capacity requested=%s effective=%s",
            requested,
            effective,
        )
    return effective


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
_session_gate_limit = _effective_session_gate_limit()
_session_gate = threading.BoundedSemaphore(_session_gate_limit)

# Background/noncritical work gets its own small gate before it can even wait
# for a real DB session. This lets heavy features run continuously without
# starving interactive Telegram commands, signal delivery proof writes, or
# signal storage. The value is intentionally smaller than the main gate.
_background_gate_limit = max(1, min(_session_gate_limit, _pool_int("DB_BACKGROUND_MAX_CONCURRENT_SESSIONS", max(1, min(2, _session_gate_limit // 2 or 1)), minimum=1)))
_background_gate = threading.BoundedSemaphore(_background_gate_limit)
_priority_admission = DBAdmissionController(
    _session_gate_limit,
    background_limit=min(_background_gate_limit, max(1, _session_gate_limit - 1)),
    analytics_limit=max(1, min(_session_gate_limit - 1 if _session_gate_limit > 1 else 1, 1)),
    analytics_enabled=bool(
        _session_gate_limit > 2
        or _database_role() == "analytics"
        or _database_role().startswith("analytics-")
        or _pool_bool("DB_ANALYTICS_ALLOW_SHARED_POOL", False)
    ),
)

_session_metrics_lock = threading.Lock()
_session_metrics: dict[str, int] = {
    "opened": 0,
    "closed": 0,
    "active": 0,
    "waiting": 0,
    "errors": 0,
    "critical_waiting": 0,
    "critical_active": 0,
    "interactive_waiting": 0,
    "interactive_active": 0,
    "background_waiting": 0,
    "background_active": 0,
    "background_dropped": 0,
    "noncritical_dropped": 0,
}
_critical_db_lock = threading.Lock()
_critical_db_inflight = 0
_legacy_priority_warning_lock = threading.Lock()
_legacy_priority_warnings: set[str] = set()
_active_holder_lock = threading.Lock()
_active_session_holders: dict[str, dict[str, Any]] = {}


def _active_holder_snapshot() -> list[dict[str, Any]]:
    now = time.monotonic()
    with _active_holder_lock:
        rows = []
        for token, item in _active_session_holders.items():
            row = dict(item)
            row["token"] = token
            row["held_seconds"] = round(max(0.0, now - float(item.get("started_mono", now))), 3)
            row.pop("started_mono", None)
            rows.append(row)
        return sorted(rows, key=lambda row: float(row.get("held_seconds", 0.0)), reverse=True)


def _log_admission_failure(*, label: str, priority: DBPriority, stage: str, timeout_s: float) -> None:
    logger.error(
        "[db_admission_timeout] label=%s priority=%s stage=%s timeout_s=%.2f admission=%s holders=%s session_metrics=%s",
        label,
        priority.value,
        stage,
        timeout_s,
        _priority_admission.snapshot(),
        _active_holder_snapshot(),
        dict(_session_metrics),
    )


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def critical_db_work_active() -> bool:
    with _critical_db_lock:
        return _critical_db_inflight > 0


def _mark_critical_db_start() -> None:
    global _critical_db_inflight
    with _critical_db_lock:
        _critical_db_inflight += 1


def _mark_critical_db_end() -> None:
    global _critical_db_inflight
    with _critical_db_lock:
        _critical_db_inflight = max(0, _critical_db_inflight - 1)


def _warn_legacy_priority_flag(flag: str) -> None:
    with _legacy_priority_warning_lock:
        if flag in _legacy_priority_warnings:
            return
        _legacy_priority_warnings.add(flag)
    logger.warning(
        "[db] get_session(%s=True) is deprecated; use get_session(priority=DBPriority.%s)",
        flag,
        "BACKGROUND" if flag == "noncritical" else flag.upper(),
    )

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

        # Keep only the first event loop backed by a persistent Railway pool.
        # Auxiliary loops use transient connections so every short-lived loop
        # cannot reserve its own independent pool.
        auxiliary_nullpool = bool(
            _engines_by_loop
            and _is_railway_runtime()
            and (
                _pool_bool("DB_AUX_LOOPS_USE_NULLPOOL", True)
                or _pool_bool("DB_AUXILIARY_NULLPOOL", True)
            )
        )
        if _is_railway_runtime():
            if pool_size > 2:
                logger.warning(
                    "[db_pool_effective_config] unsafe Railway monolith pool configuration "
                    "pool_size=%s max_overflow=%s effective=%s+%s; recommended DB_POOL_SIZE=2 DB_MAX_OVERFLOW=0",
                    pool_size,
                    max_overflow,
                    pool_size,
                    max_overflow,
                )
            else:
                logger.info(
                    "[db_pool_effective_config] Railway safe pool: pool_size=%s max_overflow=%s",
                    pool_size,
                    max_overflow,
                )
        if (pool_size == 0 and max_overflow == 0) or auxiliary_nullpool:
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
            "[db] async engine initialised loop=%s url=%s pool_size=%s max_overflow=%s auxiliary_nullpool=%s",
            loop_id,
            _masked,
            pool_size,
            max_overflow,
            auxiliary_nullpool,
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


def get_session_api_contract() -> dict[str, Any]:
    """Describe the canonical DB session API for startup/release diagnostics."""
    import inspect

    parameters = inspect.signature(get_session).parameters
    return {
        "signature_version": 3,
        "supports_priority": "priority" in parameters,
        "supports_label": "label" in parameters,
        "supports_timeout": "timeout_seconds" in parameters,
        "legacy_adapter": all(name in parameters for name in ("noncritical", "critical", "interactive")),
    }


def get_engine_inventory() -> list[dict[str, Any]]:
    """Produce an engine inventory for the release guard and /db_health.

    Returns:
        A list of dicts, each with:
        - loop_id
        - pool_type ("NullPool" or "QueuePool" or "AsyncAdaptedQueuePool")
        - pool_size
        - max_overflow
        - checked_out / checked_in (if accessible)
        - owning_runtime ("main" or "auxiliary")
    """
    inventory: list[dict[str, Any]] = []
    main_loop_id = _loop_identity()
    for loop_id, engine in list(_engines_by_loop.items()):
        pool_type = "unknown"
        pool_size = 0
        max_overflow = 0
        checked_out = None
        checked_in = None
        try:
            pool = engine.sync_engine.pool
            pool_type = type(pool).__name__
            try:
                pool_size = int(getattr(pool, "size", lambda: 0)() if callable(getattr(pool, "size", None)) else getattr(pool, "size", 0) or 0)
            except Exception:
                pass
            try:
                max_overflow = int(getattr(pool, "overflow", lambda: 0)() if callable(getattr(pool, "overflow", None)) else getattr(pool, "overflow", 0) or 0)
            except Exception:
                pass
            try:
                checked_out = int(getattr(pool, "checkedout", lambda: 0)() if callable(getattr(pool, "checkedout", None)) else getattr(pool, "checkedout", None))
            except Exception:
                pass
            try:
                checked_in = int(getattr(pool, "checkedin", lambda: 0)() if callable(getattr(pool, "checkedin", None)) else getattr(pool, "checkedin", None))
            except Exception:
                pass
        except Exception:
            pass
        owning = "main" if loop_id == main_loop_id else "auxiliary"
        inventory.append({
            "loop_id": loop_id,
            "pool_type": pool_type,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "checked_out": checked_out,
            "checked_in": checked_in,
            "owning_runtime": owning,
            "nullpool": pool_type == "NullPool" and pool_size == 0 and max_overflow == 0,
        })
    return inventory


def get_pool_diagnostics() -> dict[str, Any]:
    """Return local SQLAlchemy pool diagnostics for admin health commands."""
    loop_id = _loop_identity()
    engine = _engines_by_loop.get(loop_id)
    pool_size, max_overflow = _effective_pool_settings()
    with _session_metrics_lock:
        session_metrics = dict(_session_metrics)
    info: dict[str, Any] = {
        "configured": is_db_configured(),
        "loop_id": loop_id,
        "engine_count": len(_engines_by_loop),
        "engine_inventory": get_engine_inventory(),
        "sessionmaker_count": len(_sessionmakers_by_loop),
        "effective_pool_size": pool_size,
        "effective_max_overflow": max_overflow,
        "railway_runtime": _is_railway_runtime(),
        "public_testing_mode": _pool_bool("PUBLIC_TESTING_MODE", False),
        "database_role": _database_role(),
        "application_name": _database_application_name(),
        "nullpool": bool(pool_size == 0 and max_overflow == 0),
        "session_limit": int(_session_gate_limit),
        "background_session_limit": int(_background_gate_limit),
        "session_metrics": session_metrics,
        "priority_admission": _priority_admission.snapshot(),
        "active_session_holders": _active_holder_snapshot(),
    }
    if engine is None:
        info["engine_ready"] = False
        return info
    info["engine_ready"] = True
    try:
        pool = engine.sync_engine.pool
        info["pool_class"] = type(pool).__name__
        for attr in ("size", "checkedin", "checkedout", "overflow"):
            try:
                value = getattr(pool, attr)
                info[attr] = int(value() if callable(value) else value)
            except Exception:
                pass
        try:
            status = getattr(pool, "status", None)
            if callable(status):
                info["status"] = str(status())
        except Exception:
            pass
    except Exception as exc:
        info["pool_error"] = f"{type(exc).__name__}: {exc}"
    return info


async def collect_database_health() -> dict[str, Any]:
    """Collect local pool and optional Postgres activity metrics."""
    diagnostics = get_pool_diagnostics()
    result: dict[str, Any] = {"pool": diagnostics, "postgres": {}, "ok": bool(diagnostics.get("configured"))}
    if not diagnostics.get("configured"):
        return result
    try:
        from sqlalchemy import text

        async with get_session(priority="interactive", label="db.health", timeout_seconds=3) as session:
            activity = await session.execute(
                text(
                    """
                    SELECT state, COUNT(*) AS count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                    """
                )
            )
            result["postgres"]["activity_by_state"] = {
                str(state or "unknown"): int(count or 0)
                for state, count in activity.fetchall()
            }
            max_conn = await session.execute(text("SHOW max_connections"))
            result["postgres"]["max_connections"] = str(max_conn.scalar_one_or_none() or "")
            await session.commit()
    except Exception as exc:
        result["ok"] = False
        result["postgres"]["error"] = f"{type(exc).__name__}: {exc}"
    return result


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


class DatabaseWorkDeferred(RuntimeError):
    """Raised when lower-priority DB work is intentionally deferred."""


class NoncriticalWriteDropped(DatabaseWorkDeferred):
    """Raised when best-effort background work is dropped for foreground work."""


class AnalyticsWorkDeferred(DatabaseWorkDeferred):
    """Raised when analytics must resume after foreground pressure subsides."""


def resolve_db_priority(
    priority: DBPriority | str | None = None,
    *,
    noncritical: bool = False,
    critical: bool = False,
    interactive: bool = False,
) -> DBPriority:
    """Resolve the explicit priority API and validate legacy boolean flags."""
    selected_flags = [
        name
        for name, enabled in (
            ("noncritical", noncritical),
            ("critical", critical),
            ("interactive", interactive),
        )
        if enabled
    ]
    if priority is not None and selected_flags:
        raise ValueError("priority cannot be combined with legacy DB priority flags")
    if len(selected_flags) > 1:
        raise ValueError(
            "conflicting legacy DB priority flags: " + ", ".join(selected_flags)
        )
    if priority is not None:
        return DBAdmissionController.normalize(priority)
    if interactive:
        _warn_legacy_priority_flag("interactive")
        return DBPriority.INTERACTIVE
    if noncritical:
        _warn_legacy_priority_flag("noncritical")
        return DBPriority.BACKGROUND
    if critical:
        _warn_legacy_priority_flag("critical")
    # Existing unannotated writes are conservatively treated as critical until
    # their call sites are classified in the later ownership/migration pass.
    return DBPriority.CRITICAL


def priority_timeout_seconds(priority: DBPriority | str) -> float:
    priority = DBAdmissionController.normalize(priority)
    if priority is DBPriority.INTERACTIVE:
        return _pool_float("DB_INTERACTIVE_SESSION_GATE_TIMEOUT_SECONDS", 0.75)
    if priority is DBPriority.CRITICAL:
        return _pool_float("DB_CRITICAL_SESSION_GATE_TIMEOUT_SECONDS", 5.0)
    if priority is DBPriority.BACKGROUND:
        return _pool_float("DB_BACKGROUND_SESSION_GATE_TIMEOUT_SECONDS", 2.0)
    return _pool_float("DB_ANALYTICS_SESSION_GATE_TIMEOUT_SECONDS", 0.0)


async def _acquire_priority_cancellation_safe(
    priority: DBPriority,
    *,
    timeout_s: float,
    nonblocking: bool,
) -> bool:
    cancel_event = threading.Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            _priority_admission.acquire,
            priority,
            timeout_s=timeout_s,
            nonblocking=nonblocking,
            cancel_event=cancel_event,
        )
    )
    try:
        return bool(await asyncio.shield(worker))
    except asyncio.CancelledError:
        cancel_event.set()

        def _release_late_acquire(task: asyncio.Task[bool]) -> None:
            try:
                if task.result():
                    _priority_admission.release(priority)
            except Exception:
                pass

        worker.add_done_callback(_release_late_acquire)
        raise


async def _acquire_semaphore_cancellation_safe(
    gate: threading.BoundedSemaphore,
    *,
    timeout_s: float,
    nonblocking: bool,
) -> bool:
    if nonblocking:
        return bool(gate.acquire(blocking=False))
    worker = asyncio.create_task(asyncio.to_thread(gate.acquire, True, max(0.0, timeout_s)))
    try:
        return bool(await asyncio.shield(worker))
    except asyncio.CancelledError:
        def _release_late_acquire(task: asyncio.Task[bool]) -> None:
            try:
                if task.result():
                    gate.release()
            except Exception:
                pass

        worker.add_done_callback(_release_late_acquire)
        raise


@asynccontextmanager
async def get_session(
    *,
    priority: DBPriority | str | None = None,
    label: str | None = None,
    timeout_seconds: float | None = None,
    timeout: float | None = None,
    noncritical: bool = False,
    critical: bool = False,
    interactive: bool = False,
) -> AsyncIterator[AsyncSession]:
    """Yield a DB session admitted by an explicit four-class priority policy.

    ``priority`` is the canonical API. The three boolean arguments remain for
    compatibility, but conflicting combinations now fail instead of silently
    changing the caller's requested durability class.

    ``label`` identifies the caller's operation for metrics, diagnostic logs
    and deferred-decision tracing. Callers should provide a descriptive stable
    label. When omitted, a bounded caller-derived label is generated; the
    holder registry never records an ``unlabelled`` session.

    ``timeout_seconds`` optionally narrows or extends the admission timeout for
    one operation. ``timeout`` is a deprecated compatibility alias retained for
    stale extensions and deployment overlays; new code must use
    ``timeout_seconds``. Supplying conflicting values fails closed. The value is
    clamped to a safe non-negative duration and does not alter the global
    priority policy.
    """
    _safe_label = re.sub(
        r"[^a-zA-Z0-9_.-]+",
        "_",
        resolve_session_label(label),
    )[:64] or "unknown_session_caller"
    resolved = resolve_db_priority(
        priority,
        noncritical=noncritical,
        critical=critical,
        interactive=interactive,
    )
    default_timeout_s = priority_timeout_seconds(resolved)
    if timeout_seconds is not None and timeout is not None:
        try:
            if float(timeout_seconds) != float(timeout):
                raise ValueError("timeout and timeout_seconds cannot disagree")
        except (TypeError, ValueError):
            raise ValueError("timeout and timeout_seconds must be matching non-negative numbers") from None
    if timeout_seconds is None:
        timeout_seconds = timeout
    try:
        timeout_s = default_timeout_s if timeout_seconds is None else max(0.0, float(timeout_seconds))
    except (TypeError, ValueError):
        raise ValueError("timeout_seconds must be a non-negative number or None") from None
    deadline = time.monotonic() + timeout_s
    is_background = resolved is DBPriority.BACKGROUND
    is_analytics = resolved is DBPriority.ANALYTICS
    is_interactive = resolved is DBPriority.INTERACTIVE
    is_critical = resolved is DBPriority.CRITICAL
    drop_background = bool(
        is_background
        and _pool_bool("DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT", True)
        and _pool_bool("DB_BACKGROUND_DROP_WHEN_BUSY", True)
    )
    nonblocking = bool(is_analytics or drop_background)

    acquired = False
    bg_acquired = False
    priority_acquired = False
    priority_started = 0.0
    holder_token: str | None = None
    foreground_waiting_recorded = False
    foreground_scope = bool(
        is_critical
        or (is_interactive and _truthy_env("DB_INTERACTIVE_PAUSES_BACKGROUND", True))
    )
    if foreground_scope:
        _mark_critical_db_start()
        with _session_metrics_lock:
            key = "interactive_waiting" if is_interactive else "critical_waiting"
            _session_metrics[key] = int(_session_metrics.get(key, 0) or 0) + 1
            foreground_waiting_recorded = True

    try:
        if is_background and critical_db_work_active() and _truthy_env(
            "DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE", False
        ):
            _priority_admission.record_deferred(resolved)
            _priority_admission.record_dropped(resolved)
            with _session_metrics_lock:
                _session_metrics["noncritical_dropped"] += 1
                raise NoncriticalWriteDropped(
                    f"noncritical DB work deferred ({_safe_label}): critical/interactive DB work active"
                )

        priority_acquired = await _acquire_priority_cancellation_safe(
            resolved,
            timeout_s=max(0.0, deadline - time.monotonic()),
            nonblocking=nonblocking,
        )
        if not priority_acquired:
            with _session_metrics_lock:
                if is_background:
                    _session_metrics["background_dropped"] += 1
                    _session_metrics["noncritical_dropped"] += 1
                elif not is_analytics:
                    _session_metrics["errors"] += 1
            if is_background:
                _priority_admission.record_dropped(resolved)
                raise NoncriticalWriteDropped(
                    f"background DB work deferred ({_safe_label}): foreground lane reserved"
                )
            if is_analytics:
                raise AnalyticsWorkDeferred(
                    "analytics DB work deferred: foreground or operational work is active"
                )
            _log_admission_failure(
                label=_safe_label,
                priority=resolved,
                stage="priority_admission",
                timeout_s=timeout_s,
            )
            raise TimeoutError(
                f"Timed out waiting for {resolved.value} DB admission after {timeout_s:.2f}s label={_safe_label}"
            )
        priority_started = time.monotonic()

        if is_background:
            with _session_metrics_lock:
                _session_metrics["background_waiting"] += 1
            try:
                bg_acquired = await _acquire_semaphore_cancellation_safe(
                    _background_gate,
                    timeout_s=max(0.0, deadline - time.monotonic()),
                    nonblocking=drop_background,
                )
            finally:
                with _session_metrics_lock:
                    _session_metrics["background_waiting"] = max(
                        0, _session_metrics["background_waiting"] - 1
                    )
            if not bg_acquired:
                _priority_admission.record_deferred(resolved)
                _priority_admission.record_dropped(resolved)
                with _session_metrics_lock:
                    _session_metrics["background_dropped"] += 1
                    _session_metrics["noncritical_dropped"] += 1
                raise NoncriticalWriteDropped(
                    f"background DB work deferred ({_safe_label}): background DB gate busy"
                )
            with _session_metrics_lock:
                _session_metrics["background_active"] += 1

        main_nonblocking = bool(is_background or is_analytics)
        if not main_nonblocking:
            with _session_metrics_lock:
                _session_metrics["waiting"] += 1
        try:
            acquired = await _acquire_semaphore_cancellation_safe(
                _session_gate,
                timeout_s=max(0.0, deadline - time.monotonic()),
                nonblocking=main_nonblocking,
            )
        finally:
            if not main_nonblocking:
                with _session_metrics_lock:
                    _session_metrics["waiting"] = max(0, _session_metrics["waiting"] - 1)

        if not acquired:
            with _session_metrics_lock:
                if is_background:
                    _session_metrics["noncritical_dropped"] += 1
                elif not is_analytics:
                    _session_metrics["errors"] += 1
            if is_background:
                _priority_admission.record_deferred(resolved)
                _priority_admission.record_dropped(resolved)
                raise NoncriticalWriteDropped(
                    f"background DB work deferred ({_safe_label}): session gate busy"
                )
            if is_analytics:
                _priority_admission.record_deferred(resolved)
                raise AnalyticsWorkDeferred(
                    "analytics DB work deferred: session gate busy"
                )
            _priority_admission.record_timeout(resolved)
            _log_admission_failure(
                label=_safe_label,
                priority=resolved,
                stage="session_gate",
                timeout_s=timeout_s,
            )
            raise TimeoutError(
                f"Timed out waiting for {resolved.value} DB session after {timeout_s:.2f}s label={_safe_label}"
            )

        session_local = _get_sessionmaker_for_loop(_loop_identity())
        if session_local is None:
            raise RuntimeError("DATABASE_URL is not configured")
        with _session_metrics_lock:
            _session_metrics["opened"] += 1
            _session_metrics["active"] += 1
            if is_critical:
                _session_metrics["critical_waiting"] = max(
                    0, _session_metrics["critical_waiting"] - 1
                )
                _session_metrics["critical_active"] += 1
                foreground_waiting_recorded = False
            if is_interactive:
                _session_metrics["interactive_waiting"] = max(
                    0, _session_metrics["interactive_waiting"] - 1
                )
                _session_metrics["interactive_active"] += 1
                foreground_waiting_recorded = False
        holder_token = f"{threading.get_ident()}:{_loop_identity()}:{time.time_ns()}"
        with _active_holder_lock:
            _active_session_holders[holder_token] = {
                "label": _safe_label,
                "priority": resolved.value,
                "thread_id": int(threading.get_ident()),
                "loop_id": int(_loop_identity()),
                "started_mono": time.monotonic(),
            }
        try:
            async with session_local() as session:
                try:
                    yield session
                except Exception:
                    with _session_metrics_lock:
                        _session_metrics["errors"] += 1
                    raise
                finally:
                    await session.close()
        finally:
            with _session_metrics_lock:
                _session_metrics["closed"] += 1
                _session_metrics["active"] = max(0, _session_metrics["active"] - 1)
                if is_critical:
                    _session_metrics["critical_active"] = max(
                        0, _session_metrics["critical_active"] - 1
                    )
                if is_interactive:
                    _session_metrics["interactive_active"] = max(
                        0, _session_metrics["interactive_active"] - 1
                    )
    finally:
        if holder_token is not None:
            with _active_holder_lock:
                holder = _active_session_holders.pop(holder_token, None)
            if holder is not None:
                held_seconds = max(0.0, time.monotonic() - float(holder.get("started_mono", time.monotonic())))
                warn_after = max(0.0, float(os.getenv("DB_SESSION_HOLD_WARN_SECONDS", "10") or 10))
                if warn_after and held_seconds >= warn_after:
                    logger.warning(
                        "[db_session_long_hold] label=%s priority=%s held_seconds=%.3f",
                        holder.get("label"),
                        holder.get("priority"),
                        held_seconds,
                    )
        if acquired:
            _session_gate.release()
        if bg_acquired:
            with _session_metrics_lock:
                _session_metrics["background_active"] = max(
                    0, _session_metrics["background_active"] - 1
                )
            _background_gate.release()
        if priority_acquired:
            _priority_admission.release(
                resolved,
                held_seconds=max(0.0, time.monotonic() - priority_started),
            )
        if foreground_scope and foreground_waiting_recorded:
            with _session_metrics_lock:
                key = "interactive_waiting" if is_interactive else "critical_waiting"
                _session_metrics[key] = max(0, _session_metrics[key] - 1)
        if foreground_scope:
            _mark_critical_db_end()


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

def resolve_session_label(label: str | None) -> str:
    """Return an explicit label or derive a stable caller label.

    ``asynccontextmanager`` adds contextlib frames between a call site and the
    generator body, so walk a small bounded stack and skip session/contextlib
    internals instead of relying on a fragile fixed frame offset.
    """
    if label and str(label).strip():
        return str(label).strip()

    frame = inspect.currentframe()
    try:
        cursor = frame.f_back if frame is not None else None
        for _ in range(12):
            if cursor is None:
                break
            module = str(cursor.f_globals.get("__name__", "unknown_module"))
            function = str(cursor.f_code.co_name)
            if module != __name__ and module != "contextlib" and function not in {
                "__aenter__",
                "__anext__",
            }:
                return f"{module}.{function}:{int(cursor.f_lineno)}"
            cursor = cursor.f_back
    finally:
        del frame

    return "unknown_session_caller"

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
