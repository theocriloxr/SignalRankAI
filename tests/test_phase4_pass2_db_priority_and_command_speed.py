from __future__ import annotations

import asyncio
import functools
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_two_connection_budget_preserves_both_foreground_lanes() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(
        2,
        background_limit=1,
        analytics_limit=1,
        analytics_enabled=False,
    )

    assert controller.acquire(DBPriority.CRITICAL, timeout_s=0.01)
    assert not controller.acquire(DBPriority.ANALYTICS, timeout_s=0, nonblocking=True)
    assert controller.acquire(DBPriority.INTERACTIVE, timeout_s=0.01)
    assert not controller.acquire(DBPriority.BACKGROUND, timeout_s=0, nonblocking=True)

    snapshot = controller.snapshot()
    assert snapshot["active_total"] == 2
    assert snapshot["classes"]["critical"]["active"] == 1
    assert snapshot["classes"]["interactive"]["active"] == 1
    assert snapshot["classes"]["analytics"]["deferred"] == 1
    assert snapshot["classes"]["background"]["deferred"] == 1

    controller.release(DBPriority.INTERACTIVE, held_seconds=0.01)
    controller.release(DBPriority.CRITICAL, held_seconds=0.02)
    assert not controller.acquire(DBPriority.ANALYTICS, timeout_s=0, nonblocking=True)
    final_snapshot = controller.snapshot()
    assert final_snapshot["active_total"] == 0
    assert final_snapshot["classes"]["interactive"]["transaction_seconds_total"] >= 0.01
    assert final_snapshot["classes"]["critical"]["transaction_seconds_total"] >= 0.02


@pytest.mark.asyncio
async def test_session_pressure_admits_interactive_and_critical_while_shedding_analytics(
    monkeypatch,
) -> None:
    from db.priority import DBAdmissionController, DBPriority
    from db import session

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def close(self) -> None:
            return None

    monkeypatch.setattr(session, "_priority_admission", DBAdmissionController(2))
    monkeypatch.setattr(session, "_session_gate", threading.BoundedSemaphore(2))
    monkeypatch.setattr(session, "_background_gate", threading.BoundedSemaphore(1))
    monkeypatch.setattr(session, "_get_sessionmaker_for_loop", lambda loop_id: FakeSession)

    release = asyncio.Event()
    critical_entered = asyncio.Event()
    interactive_entered = asyncio.Event()

    async def hold(priority, entered) -> None:
        async with session.get_session(priority=priority):
            entered.set()
            await release.wait()

    critical_task = asyncio.create_task(hold(DBPriority.CRITICAL, critical_entered))
    await critical_entered.wait()
    with pytest.raises(session.AnalyticsWorkDeferred):
        async with session.get_session(priority=DBPriority.ANALYTICS):
            pass

    interactive_task = asyncio.create_task(
        hold(DBPriority.INTERACTIVE, interactive_entered)
    )
    await asyncio.wait_for(interactive_entered.wait(), timeout=0.25)
    release.set()
    await asyncio.gather(critical_task, interactive_task)

    assert session._priority_admission.snapshot()["active_total"] == 0


def test_analytics_runs_only_when_operational_lanes_are_idle() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(2)
    assert controller.acquire(DBPriority.ANALYTICS, timeout_s=0, nonblocking=True)
    assert not controller.acquire(DBPriority.BACKGROUND, timeout_s=0, nonblocking=True)
    # A borrower consumes at most one of two slots, so foreground can still
    # make progress even when already-admitted analytics is finishing.
    assert controller.acquire(DBPriority.INTERACTIVE, timeout_s=0.01)

    controller.release(DBPriority.INTERACTIVE)
    controller.release(DBPriority.ANALYTICS)


def test_cancelled_admission_wait_does_not_leak_active_capacity() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(2)
    assert controller.acquire(DBPriority.CRITICAL, timeout_s=0.01)
    cancel = threading.Event()
    result: list[bool] = []

    waiter = threading.Thread(
        target=lambda: result.append(
            controller.acquire(DBPriority.CRITICAL, timeout_s=2.0, cancel_event=cancel)
        )
    )
    waiter.start()
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if controller.snapshot()["classes"]["critical"]["waiting"] == 1:
            break
        time.sleep(0.005)
    cancel.set()
    waiter.join(timeout=0.5)

    assert result == [False]
    assert controller.snapshot()["classes"]["critical"]["active"] == 1
    controller.release(DBPriority.CRITICAL)
    snapshot = controller.snapshot()
    assert snapshot["active_total"] == 0
    assert snapshot["classes"]["critical"]["cancelled"] == 1


@pytest.mark.asyncio
async def test_async_admission_cancellation_releases_any_late_acquire(monkeypatch) -> None:
    from db.priority import DBPriority
    from db import session

    started = threading.Event()
    finish = threading.Event()
    released: list[DBPriority] = []

    class SlowAdmission:
        def acquire(self, priority, **kwargs) -> bool:
            started.set()
            finish.wait(timeout=1.0)
            return True

        def release(self, priority, **kwargs) -> None:
            released.append(priority)

    controller = SlowAdmission()
    monkeypatch.setattr(session, "_priority_admission", controller)

    async def real_to_thread(func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, call)

    # The repository test harness intentionally replaces asyncio.to_thread
    # with an inline helper. Restore real offloading for this cancellation test.
    monkeypatch.setattr(asyncio, "to_thread", real_to_thread)

    waiter = asyncio.create_task(
        session._acquire_priority_cancellation_safe(
            DBPriority.INTERACTIVE,
            timeout_s=2.0,
            nonblocking=False,
        )
    )
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and not started.is_set():
        await asyncio.sleep(0.005)
    assert started.is_set()
    assert waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    finish.set()
    await asyncio.sleep(0.075)

    assert released == [DBPriority.INTERACTIVE]


def test_priority_api_rejects_ambiguous_legacy_combinations() -> None:
    from db.priority import DBPriority
    from db.session import resolve_db_priority

    assert resolve_db_priority(interactive=True) is DBPriority.INTERACTIVE
    assert resolve_db_priority(critical=True) is DBPriority.CRITICAL
    assert resolve_db_priority(noncritical=True) is DBPriority.BACKGROUND
    assert resolve_db_priority() is DBPriority.CRITICAL
    assert resolve_db_priority("analytics") is DBPriority.ANALYTICS
    with pytest.raises(ValueError, match="conflicting"):
        resolve_db_priority(interactive=True, critical=True)
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_db_priority(DBPriority.INTERACTIVE, interactive=True)


def test_priority_timeouts_and_role_application_name(monkeypatch) -> None:
    from db.priority import DBPriority
    from db import session

    for name in (
        "DB_INTERACTIVE_SESSION_GATE_TIMEOUT_SECONDS",
        "DB_CRITICAL_SESSION_GATE_TIMEOUT_SECONDS",
        "DB_BACKGROUND_SESSION_GATE_TIMEOUT_SECONDS",
        "DB_ANALYTICS_SESSION_GATE_TIMEOUT_SECONDS",
        "DB_APP_NAME",
        "RUN_MODE",
        "RAILWAY_SERVICE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DB_ROLE", "Telegram Worker")

    assert session.priority_timeout_seconds(DBPriority.INTERACTIVE) == 0.75
    assert session.priority_timeout_seconds(DBPriority.CRITICAL) == 5.0
    assert session.priority_timeout_seconds(DBPriority.BACKGROUND) == 2.0
    assert session.priority_timeout_seconds(DBPriority.ANALYTICS) == 0.0
    assert session._engine_connect_args()["server_settings"]["application_name"] == (
        "signalrankai/telegram-worker"
    )
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "telegram")
    monkeypatch.setenv("DB_POOL_SIZE", "50")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "20")
    monkeypatch.setenv("DB_MAX_CONCURRENT_SESSIONS", "99")
    monkeypatch.delenv("DB_POOL_DISABLE_RAILWAY_CAP", raising=False)
    monkeypatch.delenv("DB_POOL_ALLOW_UNCAPPED_RAILWAY", raising=False)
    assert session._effective_session_gate_limit() == 2


def test_command_response_cache_expires_and_evicts_oldest_entry() -> None:
    from signalrank_telegram.command_resilience import CommandResponseCache

    now = [100.0]
    cache = CommandResponseCache(max_entries=2, ttl_seconds=5.0, clock=lambda: now[0])
    cache.set("a", {"text": "A"})
    now[0] += 1.0
    cache.set("b", {"text": "B"})
    assert cache.get("a").age_seconds == 1.0
    cache.set("c", {"text": "C"})

    assert cache.get("b") is None
    assert cache.get("a") is not None
    now[0] += 6.0
    assert cache.get("a") is None
    assert cache.get("c") is None


@pytest.mark.asyncio
async def test_command_acknowledgement_answers_callback_immediately() -> None:
    from signalrank_telegram.command_resilience import acknowledge_command

    events: list[str] = []

    class Query:
        async def answer(self) -> None:
            events.append("ack")

    update = SimpleNamespace(callback_query=Query(), effective_chat=None)
    assert await acknowledge_command(update, SimpleNamespace(bot=None)) is True
    events.append("work")
    assert events == ["ack", "work"]


@pytest.mark.asyncio
async def test_active_command_wrapper_acknowledges_before_handler(monkeypatch) -> None:
    from signalrank_telegram import bot, command_resilience

    events: list[str] = []

    async def acknowledge(update, context) -> bool:
        events.append("ack")
        return True

    async def handler(update, context) -> None:
        events.append("handler")

    monkeypatch.setattr(command_resilience, "acknowledge_command", acknowledge)
    wrapped = bot._audit_handler("start", handler)
    await wrapped(SimpleNamespace(message=None), SimpleNamespace())

    assert events == ["ack", "handler"]


@pytest.mark.asyncio
async def test_command_audit_is_scheduled_without_delaying_handler(monkeypatch) -> None:
    from signalrank_telegram import bot, command_resilience
    from db import session

    events: list[str] = []
    scheduled: list[asyncio.Task] = []
    block_audit = asyncio.Event()
    audit_started = asyncio.Event()

    async def acknowledge(update, context) -> bool:
        events.append("ack")
        return True

    async def handler(update, context) -> None:
        events.append("handler")

    class SlowSession:
        async def __aenter__(self):
            audit_started.set()
            await block_audit.wait()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def schedule(awaitable, *, name):
        task = asyncio.create_task(awaitable, name=name)
        scheduled.append(task)
        return task

    monkeypatch.setattr(command_resilience, "acknowledge_command", acknowledge)
    monkeypatch.setattr(command_resilience, "schedule_background_task", schedule)
    monkeypatch.setattr(session, "get_engine_for_event_loop", lambda: object())
    monkeypatch.setattr(session, "get_session", lambda **kwargs: SlowSession())
    update = SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id=42, username="tester"),
    )
    wrapped = bot._audit_handler("help", handler)

    await asyncio.wait_for(wrapped(update, SimpleNamespace(args=[])), timeout=0.25)

    assert events == ["ack", "handler"]
    assert len(scheduled) == 1
    await asyncio.wait_for(audit_started.wait(), timeout=0.25)
    assert not scheduled[0].done()
    scheduled[0].cancel()
    await asyncio.gather(*scheduled, return_exceptions=True)


@pytest.mark.asyncio
async def test_signals_command_returns_cached_response_when_db_is_busy(monkeypatch) -> None:
    from signalrank_telegram import commands
    from signalrank_telegram.command_resilience import command_response_cache

    class BusySession:
        async def __aenter__(self):
            raise TimeoutError("foreground lane occupied")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        message=message,
        callback_query=None,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(args=[])
    command_response_cache.clear()
    command_response_cache.set(
        "signals:42:active:7:8:*:all",
        {"text": "Cached signal index", "buttons": []},
    )
    monkeypatch.delenv("SIGNALS_COMMAND_LOOKBACK_DAYS", raising=False)
    monkeypatch.delenv("SIGNALS_COMMAND_LIMIT", raising=False)
    monkeypatch.setattr(commands, "_public_guard", AsyncMock(return_value=False))
    monkeypatch.setattr(commands, "get_session", lambda **kwargs: BusySession())

    await commands.signals_command(update, context)

    assert message.reply_text.await_count == 1
    assert "Cached signal index" in message.reply_text.await_args.args[0]
    assert "live data is temporarily busy" in message.reply_text.await_args.args[0]
    command_response_cache.clear()


def test_same_priority_admission_is_fifo_under_contention() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(1)
    assert controller.acquire(DBPriority.CRITICAL, timeout_s=0.01)
    order: list[str] = []
    release_first = threading.Event()

    def waiter(name: str, hold: bool = False) -> None:
        assert controller.acquire(DBPriority.CRITICAL, timeout_s=1.0)
        order.append(name)
        if hold:
            release_first.wait(timeout=1.0)
        controller.release(DBPriority.CRITICAL)

    first = threading.Thread(target=waiter, args=("first", True))
    second = threading.Thread(target=waiter, args=("second", False))
    first.start()
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if controller.snapshot()["classes"]["critical"]["waiting"] == 1:
            break
        time.sleep(0.005)
    second.start()
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if controller.snapshot()["classes"]["critical"]["waiting"] == 2:
            break
        time.sleep(0.005)

    controller.release(DBPriority.CRITICAL)
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and order != ["first"]:
        time.sleep(0.005)
    release_first.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert order == ["first", "second"]
    assert controller.snapshot()["active_total"] == 0
