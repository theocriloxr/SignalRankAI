"""Cross-replica leases for synchronous APScheduler jobs."""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from core.env import runtime_environment_name


_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_GUARD = threading.Lock()


@dataclass(frozen=True, slots=True)
class SchedulerJobLease:
    acquired: bool
    backend: str
    scope: str
    key: str


def scheduler_job_scope(job_name: str) -> str:
    explicit = str(os.getenv(f"{job_name.upper()}_LOCK_SCOPE") or "").strip()
    if explicit:
        return explicit
    project = str(
        os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_PROJECT_NAME")
        or "local"
    ).strip()
    environment = runtime_environment_name("development")
    return f"{project}:{environment}:{str(job_name).strip().lower()}"


def lock_id_for_scope(scope: str) -> int:
    """Stable 63-bit advisory-lock id for a scope string."""
    digest = hashlib.sha256(f"signalrank:scheduler:{scope}".encode("utf-8")).digest()
    return max(1, int.from_bytes(digest[:8], "big") & ((1 << 63) - 1))


def _lock_id(scope: str) -> int:
    return lock_id_for_scope(scope)


@contextmanager
def acquire_scheduler_job_lease(
    job_name: str,
    *,
    lease_seconds: int = 120,
) -> Iterator[SchedulerJobLease]:
    """Acquire one cluster-wide lease and release only our own token.

    Redis is preferred because its TTL recovers automatically after process
    termination. PostgreSQL advisory locks are the durable fallback. Production
    fails closed when neither backend is available.
    """
    scope = scheduler_job_scope(job_name)
    key = f"signalrank:scheduler-lease:{scope}"
    token = uuid.uuid4().hex
    redis_client = None
    acquired = False

    try:
        from core.redis_state import state

        redis_client = state._get_redis_sync()
    except Exception:
        redis_client = None

    if redis_client is not None:
        try:
            acquired = bool(
                redis_client.set(
                    key,
                    token,
                    ex=max(30, int(lease_seconds)),
                    nx=True,
                )
            )
            yield SchedulerJobLease(acquired, "redis", scope, key)
        finally:
            if acquired:
                try:
                    redis_client.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        key,
                        token,
                    )
                except Exception:
                    pass
        return

    connection = None
    postgres_available = False
    try:
        import psycopg2
        from config import resolve_database_url

        dsn = resolve_database_url(async_driver=False) or ""
        if dsn:
            connection = psycopg2.connect(dsn, connect_timeout=5)
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_lock_id(scope),))
                acquired = bool((cursor.fetchone() or [False])[0])
            postgres_available = True
    except Exception:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        connection = None

    if postgres_available and connection is not None:
        try:
            yield SchedulerJobLease(acquired, "postgres", scope, key)
        finally:
            try:
                if acquired:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", (_lock_id(scope),))
            finally:
                connection.close()
        return

    if runtime_environment_name("development") == "production":
        yield SchedulerJobLease(False, "unavailable", scope, key)
        return

    with _LOCAL_GUARD:
        local_lock = _LOCAL_LOCKS.setdefault(scope, threading.Lock())
    acquired = local_lock.acquire(blocking=False)
    try:
        yield SchedulerJobLease(acquired, "local", scope, key)
    finally:
        if acquired:
            local_lock.release()


__all__ = [
    "SchedulerJobLease",
    "acquire_scheduler_job_lease",
    "lock_id_for_scope",
    "scheduler_job_scope",
]
