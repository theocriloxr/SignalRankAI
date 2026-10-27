"""Backlog fairness and committed-only metrics for shadow observations."""
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from core.redis_state import state
from db.models import DecisionLog, MLShadowPrediction
from engine.shadow_outcome_worker import ShadowOutcomeWorker
from utils.timeutils import now_utc_naive


class StoreSession:
    """Awaitable adapter over real SQL transactions; no optional SQLite driver."""
    def __init__(self, session):
        self.session = session

    def add(self, value):
        self.session.add(value)

    def add_all(self, values):
        self.session.add_all(values)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def get(self, model, key):
        return self.session.get(model, key)

    async def commit(self):
        self.session.commit()


@pytest_asyncio.fixture
async def shadow_store(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    DecisionLog.__table__.create(engine)
    MLShadowPrediction.__table__.create(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session_scope(**_kwargs):
        with sessions() as session:
            try:
                yield StoreSession(session)
            finally:
                session.rollback()

    monkeypatch.setattr("db.session.get_session", session_scope)
    monkeypatch.setattr(state, "set_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(state, "get_sync", lambda *_args: None)
    yield session_scope
    engine.dispose()


def decision(row_id, **overrides):
    values = dict(id=row_id, asset="BTCUSDT", timeframe="5m", decision="rejected", reason="risk/expectancy_unavailable",
                  created_at=now_utc_naive() - timedelta(hours=2),
                  meta={"layer": "ml", "direction": "long", "entry": 100, "stop_loss": 90,
                        "take_profit": [110, 120, 130], "ml_probability": 0.7})
    values.update(overrides)
    return DecisionLog(**values)


@pytest.mark.asyncio
async def test_unresolved_oldest_batch_does_not_starve_newer_candidates(shadow_store, monkeypatch):
    async with shadow_store() as session:
        session.add_all([decision(i) for i in range(1, 6)])
        await session.commit()
    worker = ShadowOutcomeWorker()
    worker._batch_size = 2
    seen = []

    async def unresolved(rows):
        seen.append([row["id"] for row in rows])
        return []

    monkeypatch.setattr(worker, "_evaluate_rows", unresolved)
    for _ in range(4):
        assert await worker.run_once() == 0
    assert seen == [[1, 2], [3, 4], [5], [1, 2]]
    async with shadow_store() as session:
        assert (await session.scalar(select(func.count(MLShadowPrediction.id)))) == 0
        assert (await session.get(DecisionLog, 1)).meta.get("outcome_tracked_at") is None


@pytest.mark.asyncio
async def test_rotation_preserves_minimum_age_domain_and_terminal_exclusions(shadow_store):
    async with shadow_store() as session:
        session.add_all([decision(1), decision(2, decision="issued"),
                         decision(3, meta={"layer": "engine"}),
                         decision(4, meta={"layer": "ml", "outcome_tracked_at": "2026-01-01"}),
                         decision(5, created_at=now_utc_naive())])
        await session.commit()
    worker = ShadowOutcomeWorker()
    worker._scan_after_id = 1000
    assert [row["id"] for row in await worker._load_rows()] == [1]


@pytest.mark.asyncio
async def test_scan_checkpoint_survives_restart_and_revisits_pending_rows(shadow_store, monkeypatch):
    saved = {}
    monkeypatch.setattr(state, "set_sync", lambda key, value, **_kwargs: saved.update({key: value}))
    monkeypatch.setattr(state, "get_sync", saved.get)
    async with shadow_store() as session:
        session.add_all([decision(i) for i in range(1, 4)])
        await session.commit()
    first = ShadowOutcomeWorker()
    first._batch_size = 2
    assert [row["id"] for row in await first._load_rows()] == [1, 2]
    first._checkpoint_scan_cursor()
    resumed = ShadowOutcomeWorker()
    resumed._restore_scan_cursor()
    assert [row["id"] for row in await resumed._load_rows()] == [3]


@pytest.mark.parametrize("value", [None, "invalid", "-5", "nan"])
def test_missing_or_invalid_checkpoint_restarts_safe_scan(monkeypatch, value):
    monkeypatch.setattr(state, "get_sync", lambda _key: value)
    worker = ShadowOutcomeWorker()
    worker._restore_scan_cursor()
    assert worker._scan_after_id == 0


@pytest.mark.asyncio
async def test_failed_outcome_transaction_cannot_increment_metrics(shadow_store, monkeypatch):
    async with shadow_store() as session:
        session.add(decision(1))
        await session.commit()
    worker = ShadowOutcomeWorker()
    row = (await worker._load_rows())[0]
    increments = []
    monkeypatch.setattr(state, "incr_sync", lambda *args, **kwargs: increments.append((args, kwargs)))

    async def fail_commit(_session):
        raise RuntimeError("commit_failed")

    monkeypatch.setattr(StoreSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit_failed"):
        await worker._persist([(row, "tp3")])
    assert increments == []
    async with shadow_store() as session:
        assert (await session.scalar(select(func.count(MLShadowPrediction.id)))) == 0
        assert "outcome_tracked_at" not in (await session.get(DecisionLog, 1)).meta


@pytest.mark.asyncio
async def test_metrics_count_committed_rows_once_without_one_second_expiry(shadow_store, monkeypatch):
    async with shadow_store() as session:
        session.add_all([decision(1), decision(2)])
        await session.commit()
    worker = ShadowOutcomeWorker()
    rows = await worker._load_rows()
    counters = {}

    def increment(key, ex=None):
        assert ex is None, "counter increment must not become one-second TTL"
        counters[key] = counters.get(key, 0) + 1

    monkeypatch.setattr(state, "incr_sync", increment)
    assert await worker._persist([(row, "tp3") for row in rows]) == 2
    assert await worker._persist([(row, "tp3") for row in rows]) == 0
    assert counters == {"shadow:counts:false_negative": 2, "shadow:counts:total_tracked": 2}


@pytest.mark.asyncio
async def test_projection_failure_does_not_undo_authoritative_outcome(shadow_store, monkeypatch):
    async with shadow_store() as session:
        session.add(decision(1))
        await session.commit()
    worker = ShadowOutcomeWorker()
    rows = await worker._load_rows()

    def offline(*_args, **_kwargs):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(state, "incr_sync", offline)
    assert await worker._persist([(rows[0], "ambiguous")]) == 1
    async with shadow_store() as session:
        assert (await session.get(DecisionLog, 1)).meta["actual_outcome"] == "ambiguous"
        assert (await session.scalar(select(func.count(MLShadowPrediction.id)))) == 1
