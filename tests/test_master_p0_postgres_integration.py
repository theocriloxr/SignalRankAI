"""Real PostgreSQL regression flows; hermetic/mock results cannot satisfy these."""
import asyncio
from datetime import datetime, timedelta
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture
async def postgres_database():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    required = os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1"
    if not url:
        if required:
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql", "SQLite cannot certify PostgreSQL flows"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}, "integration mutations require a local isolated database"
    assert "test" in (parsed.database or "") or parsed.database == "signalrank_master_audit"
    async with get_session() as session:
        from sqlalchemy import text
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0048_runtime_schema_bridge"
    yield
    await dispose_engine_for_event_loop()


@pytest.mark.asyncio
async def test_oct1_receipt_paper_idempotency_and_missed_entry_on_postgres(postgres_database):
    from scripts.staging_oct1_incident_replay import _run_replay

    result = await _run_replay({"environment": "test", "scope": "LOCAL_REAL_POSTGRES"})
    assert result["status"] == "PASS"
    assert result["external_notifications_sent"] is False
    assert result["broker_orders_submitted"] is False
    assert all(result["assertions"].values())


@pytest.mark.asyncio
async def test_concurrent_tp_writers_cannot_expire_or_duplicate_terminal_trade(postgres_database, monkeypatch):
    from db.models import Signal, SignalLifecycle, SignalTrackingEvent
    from db.session import get_session
    from engine.signal_lifecycle import record_lifecycle_event

    monkeypatch.setenv("OUTCOME_LIFECYCLE_ENABLED", "1")
    now = datetime.utcnow()
    signal_id = str(uuid4())
    plan = {"signal_id": signal_id, "asset": "JNJ", "entry": 262.2601, "stop_loss": 262.7518,
            "take_profit": [260.8439, 259.4277, 258.0116], "direction": "short",
            "created_at": now, "expires_at": now + timedelta(hours=1)}
    async with get_session() as session:
        session.add(Signal(signal_id=signal_id, asset="JNJ", timeframe="1m", direction="short",
                           entry=plan["entry"], stop_loss=plan["stop_loss"], take_profit=json.dumps(plan["take_profit"]),
                           score=90, strategy_name="audit", strategy_group="audit", strength=1,
                           created_at=now, expires_at=plan["expires_at"]))
        session.add(SignalLifecycle(signal_id=signal_id, state="ACTIVE_TRADE", entry_touched_at=now))
        await session.commit()
    results = await asyncio.gather(*[
        record_lifecycle_event(plan, "tp1_hit", 260.8439, {"observation_price": 260.8}) for _ in range(8)
    ])
    assert sum(results) == 1
    assert not await record_lifecycle_event(plan, "expired", 262.45)
    assert await record_lifecycle_event(plan, "time_stop", 262.45)
    assert not await record_lifecycle_event(plan, "time_stop", 262.45)
    async with get_session() as session:
        lifecycle = (await session.execute(select(SignalLifecycle).where(SignalLifecycle.signal_id == signal_id))).scalar_one()
        assert lifecycle.state == "CLOSED_TIME_STOP"
        count = (await session.execute(select(func.count()).select_from(SignalTrackingEvent).where(
            SignalTrackingEvent.signal_id == signal_id, SignalTrackingEvent.event_type == "tp1_hit"))).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_stale_outcome_writer_cannot_override_active_lifecycle(postgres_database):
    from db.models import Outcome, Signal, SignalLifecycle
    from db.session import get_session
    from engine.realtime_outcome_tracker import _persist_outcome

    signal_id = str(uuid4())
    async with get_session() as session:
        session.add(Signal(signal_id=signal_id, asset="AUDIT", timeframe="1m", direction="long", entry=100,
                           stop_loss=95, take_profit="[102,104,106]", score=90, strategy_name="audit",
                           strategy_group="audit", strength=1))
        session.add(SignalLifecycle(signal_id=signal_id, state="ACTIVE_TRADE", entry_touched_at=datetime.utcnow()))
        await session.commit()
    await _persist_outcome(signal_id, "expired", 100, 99)
    async with get_session() as session:
        assert (await session.execute(select(Outcome).where(Outcome.signal_id == signal_id))).scalar_one_or_none() is None
