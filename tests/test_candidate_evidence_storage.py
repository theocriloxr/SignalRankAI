"""Exercise rejection ownership and forward cohorts on actual PostgreSQL."""
from contextlib import asynccontextmanager
from datetime import timedelta
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from db.models import DecisionLog, MLRejectedSignal
from engine import signal_deduplicator as dedup
from utils.timeutils import now_utc_naive


@pytest_asyncio.fixture
async def evidence_database(monkeypatch):
    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("PostgreSQL evidence regression requires an isolated database")
        pytest.skip("requires isolated local PostgreSQL")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.host in {"localhost", "127.0.0.1"}
    assert "test" in (parsed.database or "") and os.getenv("APP_ENV") == "test"
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0052_research_dataset_snapshots"
        factory = async_sessionmaker(connection, expire_on_commit=False, join_transaction_mode="create_savepoint")

        @asynccontextmanager
        async def scope(**kwargs):
            async with factory() as session:
                yield session

        monkeypatch.setattr(dedup, "get_session", scope)
        monkeypatch.setattr("db.session.get_session", scope)
        monkeypatch.setenv("REJECTION_LOG_WRITE_ENABLED", "1")
        monkeypatch.setenv("REJECTION_DB_BATCH_SIZE", "1")
        with dedup._REJECTION_SPOOL_LOCK:
            dedup._REJECTION_SPOOL.clear()
        try:
            yield connection, factory
        finally:
            with dedup._REJECTION_SPOOL_LOCK:
                dedup._REJECTION_SPOOL.clear()
            await transaction.rollback()
    await engine.dispose()


async def record(tracker, asset):
    return await tracker.persist_rejection(
        asset=asset, timeframe="5m", direction="long", entry_price=100,
        stop_loss=95, take_profit_levels=[110], ml_probability=0.7,
        rejection_reason="candidate_shadow_observation",
        features={"candidate_observation_key": uuid4().hex}, rejection_type="candidate_shadow",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_table", [False, True])
async def test_batch_writes_one_physical_owner_and_reloads_through_reader(evidence_database, legacy_table):
    connection, factory = evidence_database
    asset = ("EVIDENCE_" + uuid4().hex[:12]).upper()
    if legacy_table:
        # Only this test transaction sees the pre-0046 relation; rollback
        # restores the actual migration view, including on assertion failure.
        await connection.execute(text("ALTER VIEW ml_rejected_signals RENAME TO audit_saved_rejection_view"))
        await connection.execute(CreateTable(MLRejectedSignal.__table__))
    tracker = dedup.MLRejectionTracker()
    assert await record(tracker, asset) is True
    assert tracker.pending_rejection_count() == 0
    async with factory() as session:
        rows = (await session.execute(select(MLRejectedSignal).where(MLRejectedSignal.asset == asset))).scalars().all()
        assert len(rows) == 1
        assert rows[0].features["rejection_type"] == "candidate_shadow"
        owner_rows = (await session.execute(select(func.count()).select_from(DecisionLog).where(DecisionLog.asset == asset))).scalar_one()
        assert owner_rows == (0 if legacy_table else 1)


@pytest.mark.asyncio
async def test_failed_commit_preserves_spool_and_has_no_durable_observation(evidence_database):
    connection, factory = evidence_database
    asset = ("EVIDENCE_FAIL_" + uuid4().hex[:8]).upper()
    await connection.execute(text("ALTER TABLE decision_log ADD CONSTRAINT audit_reject_evidence CHECK (asset NOT LIKE 'EVIDENCE_FAIL_%')"))
    tracker = dedup.MLRejectionTracker()
    # True means queued, even if the attempted commit failed. The reader
    # cannot count the spool as durable forward proof.
    assert await record(tracker, asset) is True
    assert tracker.pending_rejection_count() == 1
    async with factory() as session:
        assert (await session.execute(select(func.count()).select_from(MLRejectedSignal).where(MLRejectedSignal.asset == asset))).scalar_one() == 0
    await connection.execute(text("ALTER TABLE decision_log DROP CONSTRAINT audit_reject_evidence"))
    assert await tracker.flush_pending_rejections(force=True) == 1
    assert tracker.pending_rejection_count() == 0


def decision(artifact, index, *, outcome=None, tracked=True, asset_class=0):
    return DecisionLog(
        asset="EVIDENCE_SCOPE", timeframe="5m", decision="rejected", reason="candidate_shadow_observation",
        created_at=now_utc_naive() - timedelta(minutes=30),
        meta={"layer": "ml", "direction": "long", "entry": 100, "stop_loss": 95, "take_profit": "110",
              "actual_outcome": outcome,
              "outcome_tracked_at": now_utc_naive().isoformat() if tracked else None,
              "features": {"rejection_type": "candidate_shadow", "candidate_artifact_hash_sha256": artifact,
                           "candidate_observation_key": f"{artifact}:{index}", "candidate_passed": index % 2 == 0,
                           "champion_passed": False, "asset_class_enc": asset_class}},
    )


@pytest.mark.asyncio
async def test_artifact_filter_precedes_limit_and_pending_outcomes_do_not_count_as_resolved(evidence_database, monkeypatch):
    _, factory = evidence_database
    from ml.candidate_forward import evaluate_candidate_forward_evidence
    artifact = uuid4().hex
    monkeypatch.setenv("ML_CANDIDATE_FORWARD_MAX_ROWS", "100")
    async with factory() as session:
        session.add_all([decision("other-model", i, outcome="win") for i in range(105)])
        session.add_all([
            decision(artifact, 0, outcome="win"),
            decision(artifact, 1, outcome="loss"),
            decision(artifact, 2, outcome=None, tracked=False, asset_class=1),
            decision(artifact, 3, outcome="win", tracked=False, asset_class=2),
        ])
        await session.commit()
    # Executes the real JSON projection, releases the read transaction, then
    # consumes plain snapshots without detached ORM lazy loads.
    evidence = await evaluate_candidate_forward_evidence({"artifact_hash_sha256": artifact, "trained_at": now_utc_naive()-timedelta(hours=1)})
    assert evidence["observations"] == 4
    assert evidence["resolved"] == 2
    assert evidence["asset_class_count"] == 1
    assert evidence["candidate_pass_rate"] == 0.5
    assert evidence["candidate"]["decision_stats"]["resolved"] == 1
    assert evidence["candidate"]["decision_stats"]["profit_factor"] is None
    assert evidence["eligible"] is False


@pytest.mark.asyncio
async def test_oversized_artifact_cohort_cannot_qualify_from_truncated_history(evidence_database, monkeypatch):
    _, factory = evidence_database
    from ml.candidate_forward import evaluate_candidate_forward_evidence
    artifact = uuid4().hex
    monkeypatch.setenv("ML_CANDIDATE_FORWARD_MAX_ROWS", "100")
    async with factory() as session:
        session.add_all([decision(artifact, i, outcome="win" if i % 2 else "loss") for i in range(101)])
        await session.commit()
    result = await evaluate_candidate_forward_evidence({"artifact_hash_sha256": artifact, "trained_at": now_utc_naive()-timedelta(hours=1)})
    assert result["eligible"] is False
    assert result["reasons"] == ["candidate_observation_limit_exceeded"]
    assert result["observations_scanned"] == 101


@pytest.mark.asyncio
async def test_future_observations_and_labels_cannot_qualify_model(evidence_database):
    _, factory = evidence_database
    from ml.candidate_forward import evaluate_candidate_forward_evidence
    artifact = uuid4().hex
    future_decision = decision(artifact, 0, outcome="win")
    future_decision.created_at = now_utc_naive() + timedelta(hours=1)
    future_label = decision(artifact, 1, outcome="win")
    future_label.meta["outcome_tracked_at"] = (now_utc_naive()+timedelta(hours=1)).isoformat()
    async with factory() as session:
        session.add_all([future_decision, future_label])
        await session.commit()
    result = await evaluate_candidate_forward_evidence({"artifact_hash_sha256": artifact, "trained_at": now_utc_naive()-timedelta(hours=1)})
    assert result["observations"] == 1 and result["resolved"] == 0
    assert result["eligible"] is False
    assert result["statistics_scope"] == "shadow_barrier_labels_gross_of_costs"
