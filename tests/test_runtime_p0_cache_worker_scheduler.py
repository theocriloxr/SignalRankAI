from __future__ import annotations

import asyncio
import json
import sys
import threading
import types

import pytest

from runtime.dispatcher import dispatch
from runtime.roles import (
    RunMode,
    SchedulerOwner,
    scheduler_ownership,
)
from runtime.scheduler import (
    PostgresAdvisorySchedulerLease,
    SchedulerOwnershipError,
    run_async,
)


class _FakeState:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}
        self.thread_ids: list[int] = []

    def get_sync(self, key: str) -> str | None:
        self.thread_ids.append(threading.get_ident())
        return self.values.get(key)

    def set_sync(self, key: str, value: str, ex: int | None = None) -> None:
        self.thread_ids.append(threading.get_ident())
        self.values[key] = value
        self.expirations[key] = ex

    def incr_sync(self, key: str, ex: int | None = None) -> int:
        self.thread_ids.append(threading.get_ident())
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        self.expirations[key] = ex
        return value


@pytest.mark.asyncio
async def test_redis_cache_uses_sync_state_api_without_awaiting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import redis_cache

    fake = _FakeState()
    monkeypatch.setattr(redis_cache, "state", fake)

    await redis_cache.cache_set("cache:contract-key", {"answer": 42}, "signal")
    assert fake.expirations["cache:contract-key"] == 900
    assert json.loads(fake.values["cache:contract-key"])["value"] == {"answer": 42}
    assert await redis_cache.cache_get("cache:contract-key") == {"answer": 42}

    await redis_cache.record_cache_hit()
    await redis_cache.record_cache_miss()
    stats = await redis_cache.cache_stats()
    assert stats == {
        "hits": 1,
        "misses": 1,
        "evictions": 0,
        "hit_rate": 50.0,
    }
    assert fake.thread_ids
    assert len(fake.thread_ids) >= 7


def test_dispatch_preserves_legacy_worker_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    worker_module = types.ModuleType("worker.worker")
    worker_module.main = lambda: calls.append("worker")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "worker.worker", worker_module)

    delivery_module = __import__("runtime.delivery", fromlist=["run"])
    monkeypatch.setattr(
        delivery_module,
        "run",
        lambda: calls.append("delivery"),
    )

    dispatch("worker")
    dispatch("delivery")
    dispatch(RunMode.DELIVERY, legacy_worker=True)

    assert calls == ["worker", "delivery", "worker"]


def test_main_forwards_original_worker_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main as entrypoint
    import runtime.dispatcher as dispatcher_module

    calls: list[tuple[str, bool]] = []
    monkeypatch.setenv("RUN_MODE", "worker")
    monkeypatch.setattr(entrypoint, "_infer_run_mode", lambda: "delivery")
    monkeypatch.setattr(entrypoint, "_check_database_configured", lambda: True)
    monkeypatch.setattr(
        dispatcher_module,
        "dispatch",
        lambda mode, legacy_worker=False: calls.append((mode, legacy_worker)),
    )

    auto_ops = types.ModuleType("db.auto_ops")
    auto_ops.run_startup_ops = lambda _mode: None  # type: ignore[attr-defined]
    selfcheck = types.ModuleType("data.startup_selfcheck")
    selfcheck.run_startup_data_selfcheck = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db.auto_ops", auto_ops)
    monkeypatch.setitem(sys.modules, "data.startup_selfcheck", selfcheck)

    entrypoint.main()

    assert calls == [("worker", True)]


def test_scheduler_ownership_defaults_to_one_monolith() -> None:
    default = scheduler_ownership({})
    assert default.owner is SchedulerOwner.MONOLITH
    assert default.lease_required is False
    assert default.allows(RunMode.ALL_DEV)
    assert not default.allows(RunMode.SCHEDULER)

    standalone = scheduler_ownership({"SCHEDULER_OWNER": "scheduler"})
    assert standalone.owner is SchedulerOwner.STANDALONE
    assert standalone.lease_required is True
    assert standalone.allows(RunMode.SCHEDULER)
    assert not standalone.allows(RunMode.ALL_DEV)
    assert (
        scheduler_ownership({"RUN_MODE": "scheduler"}).owner
        is SchedulerOwner.STANDALONE
    )


def test_postgres_scheduler_lease_uses_session_scoped_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[tuple[str, tuple | None]] = []

    class FakeCursor:
        def __init__(self) -> None:
            self.statement = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, statement: str, params: tuple | None = None) -> None:
            self.statement = statement
            statements.append((statement, params))

        def fetchone(self):
            if "pg_try_advisory_lock" in self.statement:
                return (True,)
            return (1,)

    class FakeConnection:
        autocommit = False

        def __init__(self) -> None:
            self.closed = False

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    psycopg = types.ModuleType("psycopg2")
    psycopg.connect = lambda dsn, connect_timeout: connection  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg)

    lease = PostgresAdvisorySchedulerLease(lock_id=321, dsn="postgresql://test")
    assert lease.acquire() is True
    assert connection.autocommit is True
    assert lease.is_held() is True
    lease.release()

    assert connection.closed is True
    assert any("pg_try_advisory_lock" in statement for statement, _ in statements)
    assert any("pg_advisory_unlock" in statement for statement, _ in statements)


@pytest.mark.asyncio
async def test_standalone_scheduler_requires_explicit_handoff() -> None:
    with pytest.raises(SchedulerOwnershipError, match="owned by the monolith"):
        await run_async(
            asyncio.Event(),
            environ={},
            scheduler_factory=lambda: None,  # type: ignore[arg-type,return-value]
        )


@pytest.mark.asyncio
async def test_standalone_scheduler_starts_only_after_singleton_lease() -> None:
    stop = asyncio.Event()
    started = asyncio.Event()

    class FakeLease:
        lock_id = 123

        def __init__(self) -> None:
            self.acquire_calls = 0
            self.release_calls = 0

        def acquire(self) -> bool:
            self.acquire_calls += 1
            return self.acquire_calls >= 2

        def is_held(self) -> bool:
            return True

        def release(self) -> None:
            self.release_calls += 1

    class FakeScheduler:
        def __init__(self) -> None:
            self.running = False
            self.shutdown_wait: bool | None = None

        def start(self) -> None:
            self.running = True
            started.set()

        def shutdown(self, wait: bool = True) -> None:
            self.shutdown_wait = wait
            self.running = False

    lease = FakeLease()
    scheduler = FakeScheduler()
    task = asyncio.create_task(
        run_async(
            stop,
            environ={
                "SCHEDULER_OWNER": "scheduler",
                "SCHEDULER_LEASE_RETRY_SECONDS": "0.01",
                "SCHEDULER_LEASE_HEALTH_SECONDS": "0.01",
            },
            scheduler_factory=lambda: scheduler,
            lease_factory=lambda: lease,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    stop.set()
    await asyncio.wait_for(task, timeout=1)

    assert lease.acquire_calls == 2
    assert lease.release_calls == 1
    assert scheduler.shutdown_wait is False
    assert scheduler.running is False
