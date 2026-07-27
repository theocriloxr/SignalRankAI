"""Lease-guarded scheduler role adapter.

The production default remains the single-process monolith.  An explicit
``RUN_MODE=scheduler`` process (or ``SCHEDULER_OWNER=scheduler`` hand-off) may
register jobs only while it holds the deployment-wide PostgreSQL advisory
lease.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
from typing import Awaitable, Callable, Mapping, Protocol

from runtime.roles import SchedulerOwner, scheduler_ownership

logger = logging.getLogger(__name__)

_DEFAULT_LEASE_ID = 915_337_122


class SchedulerOwnershipError(RuntimeError):
    """Raised when a standalone scheduler starts without owning registration."""


class SchedulerLike(Protocol):
    running: bool

    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


class SchedulerLease(Protocol):
    def acquire(self) -> bool: ...

    def is_held(self) -> bool: ...

    def release(self) -> None: ...


class PostgresAdvisorySchedulerLease:
    """Session-scoped PostgreSQL advisory lock used as the scheduler lease."""

    def __init__(self, *, lock_id: int | None = None, dsn: str | None = None) -> None:
        self.lock_id = int(
            lock_id
            if lock_id is not None
            else os.getenv("SCHEDULER_LEASE_LOCK_ID", str(_DEFAULT_LEASE_ID))
        )
        self._dsn_override = str(dsn or "").strip()
        self._connection = None
        self._held = False
        self._lock = threading.Lock()

    def _resolve_dsn(self) -> str:
        if self._dsn_override:
            return self._dsn_override
        from config import resolve_database_url

        return str(resolve_database_url(async_driver=False) or "").strip()

    def _close_unlocked(self) -> None:
        connection = self._connection
        self._connection = None
        self._held = False
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def acquire(self) -> bool:
        """Try to acquire the singleton lease without blocking another owner."""

        with self._lock:
            if self._held and self._connection is not None:
                return True
            self._close_unlocked()
            dsn = self._resolve_dsn()
            if not dsn:
                logger.error("[scheduler] lease unavailable: database is not configured")
                return False
            try:
                import psycopg2

                timeout = max(
                    1,
                    int(os.getenv("SCHEDULER_LEASE_CONNECT_TIMEOUT_SECONDS", "5") or 5),
                )
                connection = psycopg2.connect(dsn, connect_timeout=timeout)
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", (self.lock_id,))
                    acquired = bool((cursor.fetchone() or (False,))[0])
                if not acquired:
                    connection.close()
                    return False
                self._connection = connection
                self._held = True
                return True
            except Exception as exc:
                self._close_unlocked()
                logger.warning(
                    "[scheduler] lease acquisition failed error=%s",
                    type(exc).__name__,
                )
                return False

    def is_held(self) -> bool:
        """Verify that the lock-owning database session is still alive."""

        with self._lock:
            if not self._held or self._connection is None:
                return False
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                return True
            except Exception:
                self._close_unlocked()
                return False

    def release(self) -> None:
        """Release the advisory lock and close its owning connection."""

        with self._lock:
            connection = self._connection
            try:
                if self._held and connection is not None:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s)",
                            (self.lock_id,),
                        )
                        cursor.fetchone()
            except Exception:
                pass
            finally:
                self._close_unlocked()


def _canonical_scheduler_factory() -> SchedulerLike:
    """Load the current scheduler composition only after lease acquisition."""

    from railway_main import _build_scheduler

    return _build_scheduler()


async def _wait_for_stop(stop_event: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0.05, timeout))
        return True
    except asyncio.TimeoutError:
        return False


async def _build_scheduler(
    factory: Callable[[], SchedulerLike | Awaitable[SchedulerLike]],
) -> SchedulerLike:
    scheduler = factory()
    if inspect.isawaitable(scheduler):
        scheduler = await scheduler
    return scheduler


async def run_async(
    stop_event: asyncio.Event | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    scheduler_factory: Callable[
        [], SchedulerLike | Awaitable[SchedulerLike]
    ] | None = None,
    lease_factory: Callable[[], SchedulerLease] | None = None,
) -> None:
    """Run the standalone scheduler while its singleton lease is healthy."""

    stop = stop_event or asyncio.Event()
    if stop.is_set():
        return
    ownership = scheduler_ownership(environ)
    if ownership.owner is SchedulerOwner.DISABLED:
        logger.info("[scheduler] disabled by ownership contract")
        return
    if ownership.owner is not SchedulerOwner.STANDALONE:
        raise SchedulerOwnershipError(
            "scheduler registration is owned by the monolith; set "
            "SCHEDULER_OWNER=scheduler only when handing ownership to a "
            "standalone scheduler service"
        )

    factory = scheduler_factory or _canonical_scheduler_factory
    lease = (
        lease_factory()
        if lease_factory is not None
        else PostgresAdvisorySchedulerLease()
    )
    env = os.environ if environ is None else environ
    retry_seconds = max(
        0.1,
        float(env.get("SCHEDULER_LEASE_RETRY_SECONDS", "15") or 15),
    )
    health_seconds = max(
        0.1,
        float(env.get("SCHEDULER_LEASE_HEALTH_SECONDS", "10") or 10),
    )

    while not stop.is_set():
        acquired = await asyncio.to_thread(lease.acquire)
        if not acquired:
            logger.info(
                "[scheduler] singleton lease busy; retrying in %.1fs",
                retry_seconds,
            )
            if await _wait_for_stop(stop, retry_seconds):
                return
            continue

        scheduler: SchedulerLike | None = None
        lease_lost = False
        try:
            scheduler = await _build_scheduler(factory)
            if not bool(getattr(scheduler, "running", False)):
                scheduler.start()
            logger.info(
                "[scheduler] started owner=%s lease_id=%s",
                ownership.owner.value,
                getattr(lease, "lock_id", "custom"),
            )
            while not stop.is_set():
                if await _wait_for_stop(stop, health_seconds):
                    break
                if not await asyncio.to_thread(lease.is_held):
                    lease_lost = True
                    logger.error(
                        "[scheduler] singleton lease lost; stopping job registration"
                    )
                    break
                if not bool(getattr(scheduler, "running", True)):
                    lease_lost = True
                    logger.error(
                        "[scheduler] scheduler stopped unexpectedly; reacquiring lease"
                    )
                    break
        finally:
            if scheduler is not None and bool(
                getattr(scheduler, "running", False)
            ):
                try:
                    scheduler.shutdown(wait=False)
                except Exception as exc:
                    logger.warning(
                        "[scheduler] shutdown failed error=%s",
                        type(exc).__name__,
                    )
            await asyncio.to_thread(lease.release)
            logger.info("[scheduler] stopped and singleton lease released")

        if stop.is_set():
            return
        if lease_lost and await _wait_for_stop(stop, retry_seconds):
            return


def run() -> None:
    asyncio.run(run_async())


start = run

__all__ = [
    "PostgresAdvisorySchedulerLease",
    "SchedulerLease",
    "SchedulerLike",
    "SchedulerOwnershipError",
    "run",
    "run_async",
    "start",
]
