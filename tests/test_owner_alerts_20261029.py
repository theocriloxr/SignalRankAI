"""Owner alerts for a stalled or silent engine, provider outages and old queue items.

The 22–28 Oct engine hang was found by hand six days later. These tests check
the owner is told: by the engine before its watchdog exits, and by the worker
when the engine heartbeat goes missing, stale or stalled, or a delivery queue
holds old work. Alerts are de-duplicated and end with a runbook line.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from observability import owner_alerts

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def outbox(monkeypatch):
    """Capture Telegram sends and use the in-process de-duplication store."""
    from core import health_notifications
    from core.redis_state import state

    sent: list[tuple[int, str]] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.OWNER_IDS", {101, 202})
    monkeypatch.setattr(state, "_get_redis_sync", lambda: None)
    monkeypatch.setattr(health_notifications, "_LOCAL", {})

    def post(_token, chat_id, text):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(owner_alerts, "_telegram_post", post)
    return sent


def _cycle(status: str, minutes_ago: float, **extra) -> str:
    stamp = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return json.dumps({"status": status, "started_at": stamp, **extra})


def test_heartbeat_findings(monkeypatch):
    monkeypatch.delenv("OWNER_ALERT_ENGINE_SILENT_SECONDS", raising=False)
    find = lambda raw: owner_alerts.engine_heartbeat_finding(raw, now=NOW)  # noqa: E731
    assert find(None)["status"] == "missing"
    assert find(b"") ["status"] == "missing"
    assert find("not json")["status"] == "missing"
    assert find(_cycle("completed", 2)) is None
    assert find(_cycle("skipped", 2)) is None  # alive; readiness names the reason
    stale = find(_cycle("completed", 20))
    assert stale == {"status": "completed", "age_seconds": 1200, "limit_seconds": 900.0}
    stalled = find(_cycle("stalled", 1, stall_stage="pipeline:BTCUSDT"))
    assert stalled["status"] == "stalled" and stalled["stall_stage"] == "pipeline:BTCUSDT"
    assert find(_cycle("skipped", 30))["status"] == "skipped"
    monkeypatch.setenv("OWNER_ALERT_ENGINE_SILENT_SECONDS", "10")  # floor is five minutes
    assert find(_cycle("completed", 4)) is None


def test_alerts_are_deduplicated_and_carry_the_runbook(outbox):
    finding = {"status": "missing", "age_seconds": None, "limit_seconds": 900.0}
    assert owner_alerts.engine_silent_alert(finding) == 2
    assert owner_alerts.engine_silent_alert(finding) == 0  # same status within the hour
    assert sorted(chat for chat, _ in outbox) == [101, 202]
    text = outbox[0][1]
    assert "no heartbeat at all" in text and owner_alerts.RUNBOOK["engine_silent"] in text
    assert "test-token" not in text


def test_no_token_or_owners_sends_nothing(outbox, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert owner_alerts.send_owner_alert("queue_age", {"queue": "x"}, "hello") == 0
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.OWNER_IDS", set())
    assert owner_alerts.send_owner_alert("queue_age", {"queue": "x"}, "hello") == 0
    assert outbox == []


def test_a_failed_send_does_not_stop_the_other_owners(outbox, monkeypatch):
    def flaky(_token, chat_id, text):
        if chat_id == 101:
            raise ConnectionError("network down")
        outbox.append((chat_id, text))
        return True

    monkeypatch.setattr(owner_alerts, "_telegram_post", flaky)
    assert owner_alerts.queue_age_alert({"queue": "event_outbox", "age_seconds": 900, "backlog": 4,
                                         "limit_seconds": 300.0}) == 1
    assert outbox[0][0] == 202 and "15 min old" in outbox[0][1] and "4 items waiting" in outbox[0][1]


def test_the_engine_alerts_the_owner_before_the_watchdog_exits(outbox, monkeypatch):
    import engine.core as engine_core
    from engine import stall_watchdog

    events: list[str] = []
    monkeypatch.setattr(engine_core.state, "set_sync", lambda *a, **k: True)
    monkeypatch.setenv("ENGINE_STALL_SECONDS", "120")
    monkeypatch.setenv("ENGINE_STALL_ACTION", "exit")
    stall_watchdog.mark("pipeline:EURUSD")
    with stall_watchdog._lock:
        stall_watchdog._state["at"] -= 600

    def exit_fn(code):
        events.append(f"exit:{code}")

    original = owner_alerts.engine_stall_alert
    monkeypatch.setattr(owner_alerts, "engine_stall_alert",
                        lambda details: (events.append("alert"), original(details))[1])
    assert stall_watchdog.check(engine_core._publish_engine_stall, exit_fn=exit_fn)
    assert events == ["alert", "exit:70"]
    assert len(outbox) == 2
    assert "Engine stalled" in outbox[0][1] and "pipeline:EURUSD" in outbox[0][1]
    assert "exiting so Railway restarts it" in outbox[0][1]
    stall_watchdog.mark("test_done")


def test_provider_outage_alert_carries_its_runbook():
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    assert "RUNBOOK['provider_outage']" in source


class _FakeStreamClient:
    def __init__(self, pending, groups, unread):
        self._pending, self._groups, self._unread = pending, groups, unread

    async def xpending(self, name, group):
        return self._pending

    async def xinfo_groups(self, name):
        return self._groups

    async def xrange(self, name, min, max, count):
        assert min.startswith("(") and max == "+" and count == 1
        return self._unread


def _stream(client):
    from core.redis_streams import RecoverableStream

    stream = RecoverableStream(name="s", group="g", redis_url="redis://unused")
    stream._client = client
    return stream


def test_stream_age_covers_unacknowledged_and_unread_messages():
    now_ms = 1_800_000_000_000
    caught_up = _FakeStreamClient({"pending": 0}, [{"name": "g", "last-delivered-id": f"{now_ms}-0"}], [])
    assert asyncio.run(_stream(caught_up).oldest_unprocessed_age_seconds(now_ms)) is None
    unacked = _FakeStreamClient({"pending": 2, "min": f"{now_ms - 400_000}-0"},
                                [{"name": "g", "last-delivered-id": f"{now_ms - 1000}-0"}], [])
    assert asyncio.run(_stream(unacked).oldest_unprocessed_age_seconds(now_ms)) == 400.0
    unread = _FakeStreamClient({"pending": 0}, [{"name": "other", "last-delivered-id": "0-0"},
                                                {"name": "g", "last-delivered-id": f"{now_ms - 900_000}-0"}],
                               [(f"{now_ms - 700_000}-3", {"payload": "{}"})])
    assert asyncio.run(_stream(unread).oldest_unprocessed_age_seconds(now_ms)) == 700.0


def test_worker_pass_alerts_on_a_silent_engine_and_old_queues(outbox, monkeypatch):
    async def queues():
        return [{"queue": "telegram_updates", "age_seconds": 600, "backlog": None, "limit_seconds": 300.0}]

    monkeypatch.setattr(owner_alerts, "queue_age_findings", queues)
    result = asyncio.run(owner_alerts.run_checks_once(read_heartbeat=lambda: None))
    assert result["engine"]["status"] == "missing"
    assert [q["queue"] for q in result["queues"]] == ["telegram_updates"]
    texts = [text for _, text in outbox]
    assert sum("Engine not producing signals" in t for t in texts) == 2
    assert sum("telegram_updates oldest item is 10 min old" in t for t in texts) == 2


def test_worker_registers_the_owner_alert_loop():
    source = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8")
    assert '_env_bool("OWNER_ALERTS_ENABLED", True)' in source
    assert '_register_task("owner_alerts", lambda: self._owner_alerts_loop(), restart_on_failure=True)' in source


@pytest.mark.asyncio
async def test_event_outbox_age_on_real_postgres():
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert os.getenv("APP_ENV") == "test"
    assert parsed.host in {"127.0.0.1", "localhost"} and "test" in (parsed.database or "")
    entry = f"owner-alert-{uuid4().hex[:12]}"
    try:
        async with get_session() as session:
            await session.execute(text(
                "INSERT INTO event_outbox(entry_id, event_type, partition_key, idempotency_key, occurred_at, "
                "status, created_at) VALUES(:e, 'test', 'p', :e, NOW(), 'pending', NOW() - INTERVAL '20 minutes')"
            ), {"e": entry})
            await session.commit()
        age, backlog = await owner_alerts.event_outbox_oldest_age_seconds()
        assert age is not None and age >= 1190 and backlog >= 1
        findings = await owner_alerts.queue_age_findings()
        assert any(f["queue"] == "event_outbox" and f["age_seconds"] >= 1190 for f in findings)
    finally:
        async with get_session() as session:
            await session.execute(text("DELETE FROM event_outbox WHERE entry_id=:e"), {"e": entry})
            await session.commit()
        await dispose_engine_for_event_loop()
