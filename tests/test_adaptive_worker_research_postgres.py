from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def worker_database():
    """Migrate an owned database, leaving the suite's database untouched."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("isolated PostgreSQL required")
        pytest.skip("isolated PostgreSQL not configured")
    assert os.getenv("APP_ENV") == "test"
    parsed = make_url(database_url)
    assert parsed.get_backend_name() == "postgresql" and parsed.host in {"127.0.0.1", "localhost"}
    assert "test" in (parsed.database or "") or parsed.database == "signalrank_master_audit"
    database = "signalrank_research_test_" + uuid4().hex[:16]
    admin = create_async_engine(parsed.set(drivername="postgresql+asyncpg", database="postgres"),
                                isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database}"'))
        created = True
        owned_url = parsed.set(database=database)
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH"}}
        env.update(APP_ENV="test", ENVIRONMENT="test", SIGNALRANK_ALLOW_DOTENV="0",
                   GLOBAL_EXECUTION_KILL_SWITCH="1", REAL_EXECUTION_ENABLED="0",
                   AUTO_EXECUTION_ENABLED="0", AUTO_TRADE_ENABLED="0", COPY_TRADE_ENABLED="0",
                   PROP_EXECUTION_ENABLED="0", REAL_PAYOUTS_ENABLED="0",
                   SIGNALRANK_DISABLE_BACKGROUND_THREADS="1",
                   DATABASE_URL=owned_url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
                   DATABASE_MIGRATION_URL=owned_url.set(drivername="postgresql").render_as_string(hide_password=False))
        migration = await asyncio.to_thread(subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1], env=env, text=True, capture_output=True, timeout=120)
        assert migration.returncode == 0, "fresh research database migration failed"
        engine = create_async_engine(owned_url.set(drivername="postgresql+asyncpg"))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            async with admin.connect() as connection:
                await connection.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database AND pid<>pg_backend_pid()"), {"database": database})
                await connection.execute(text(f'DROP DATABASE "{database}"'))
        await admin.dispose()


def use_database(monkeypatch, database):
    from engine.adaptive import learning, repository

    @asynccontextmanager
    async def get_session(**kwargs):
        async with database() as session:
            yield session

    monkeypatch.setattr(learning, "get_session", get_session)
    monkeypatch.setattr(repository, "get_session", get_session)
    return get_session


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wrong_calibration", "uncalibrated", "bounded_window", "version_sample"])
async def test_actual_health_reads_canonical_probabilities_and_a_bounded_unique_window(monkeypatch, worker_database, mode):
    from db.models import Signal, Outcome, User, SignalDelivery, AdaptiveAssetProfile, AdaptiveSignalEvidence
    from engine.adaptive import learning, repository
    from utils.timeutils import now_utc_naive
    sessions = use_database(monkeypatch, worker_database)
    monkeypatch.setenv("ML_PUBLIC_CALIBRATION_METRICS_REQUIRED", "1")
    monkeypatch.setenv("ML_MIN_CALIBRATION_VALIDATION_ROWS", "100")
    monkeypatch.setattr(repository, "state", SimpleNamespace(get_sync=lambda _: None, set_sync=lambda *a, **kw: True))
    invalidated = []
    monkeypatch.setattr(repository, "invalidate_profile_cache", invalidated.append)
    count = 350 if mode == "bounded_window" else 70 if mode == "version_sample" else 35
    start = now_utc_naive() - timedelta(days=20)
    async with sessions() as session:
        user = User(telegram_user_id=987654320)
        session.add(user)
        session.add(AdaptiveAssetProfile(profile_id="health-probability", asset="AUDITPROB", asset_class="crypto",
                                         version=1, state="CANARY", is_current=True))
        await session.flush()
        for i in range(count):
            identifier = str(uuid4())
            version = "bad-small" if mode == "version_sample" and i < 20 else "good-large"
            calibrated = mode in {"wrong_calibration", "version_sample"}
            probability = 0.05 if mode == "wrong_calibration" or version == "bad-small" else 0.99
            session.add(Signal(signal_id=identifier, asset="AUDITPROB", asset_class="crypto", timeframe="1h",
                direction="long", entry=100, stop_loss=90, take_profit="[110]", score=80, strength=0.8,
                strategy_name="audit", strategy_group="trend", regime="trend", status="closed",
                ml_probability_calibrated=probability if calibrated else None, ml_calibration_validated=calibrated,
                ml_calibration_version=version if calibrated else None, ml_calibration_validation_rows=250,
                ml_calibration_brier=0.16, ml_calibration_ece=0.04, created_at=start + timedelta(minutes=20 * i)))
            await session.flush()
            loss = mode == "bounded_window" and i < 100
            session.add(Outcome(signal_id=identifier, status="loss" if loss else "win", r_multiple=-1 if loss else 0.5,
                provenance="delivered", closed_at=start + timedelta(minutes=20 * i + 10), performance_inclusion_status="eligible"))
            session.add(SignalDelivery(user_id=user.id, signal_id=identifier, sent_ok=True, delivery_state="CONFIRMED"))
            # Two component rows must never turn one signal into two observations.
            for component in ("a", "b"):
                session.add(AdaptiveSignalEvidence(signal_id=identifier, asset="AUDITPROB", timeframe="1h", strategy_id=component,
                    strategy_version="1", family="trend", direction="long", setup_type="audit", confidence=1.0 if calibrated else 0.0,
                    raw_score=80, profile_id="health-probability", profile_version=1, duplicate_fingerprint=uuid4().hex))
        await session.commit()
    result = await learning.monitor_profile_health()
    report = result["profile_diagnostics"][0]
    assert report["sample_size"] == min(250, count)
    assert report["expectancy_r"] == 0.5
    assert not report["broker_fills_certified"]
    if mode == "wrong_calibration":
        assert result["suspended_assets"] == ["AUDITPROB"] and invalidated == ["AUDITPROB"]
        assert report["brier_score"] == pytest.approx(0.9025)
        async with sessions() as session:
            details = (await session.execute(text("SELECT metrics FROM adaptive_drift_events"))).scalar_one()
            assert details["calibration_versions"]["good-large"]["sample_size"] == 35
    else:
        assert result["suspended_assets"] == [] and invalidated == []
        if mode == "version_sample":
            assert report["qualified_calibration_version_count"] == 1
            assert report["brier_score"] == pytest.approx(0.0001)
        else:
            assert report["brier_score"] is None and report["calibration_status"] == "UNAVAILABLE"


async def seed_research_outcomes(get_session, asset):
    from db.models import Signal, Outcome
    from utils.timeutils import now_utc_naive
    start = now_utc_naive() - timedelta(days=10)
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0050_profile_health_index"
        for i in range(160):
            signal_id = str(uuid4())
            session.add(Signal(signal_id=signal_id, asset=asset, asset_class="crypto", timeframe="1h", direction="long",
                               entry=100, stop_loss=90, take_profit="[110]", score=80, strength=0.8,
                               strategy_name="audit", strategy_group="trend", regime="trend", status="shadow",
                               created_at=start + timedelta(hours=i)))
            await session.flush()
            session.add(Outcome(signal_id=signal_id, status="win" if i % 5 else "loss",
                                r_multiple=0.4 if i % 5 else -0.5, provenance="shadow",
                                closed_at=start + timedelta(hours=i, minutes=30), performance_inclusion_status="eligible"))
        await session.commit()


@pytest.mark.asyncio
async def test_actual_worker_persists_a_nonpromotable_candidate_and_reuses_trial(monkeypatch, worker_database):
    from engine.adaptive import learning, repository
    get_session = use_database(monkeypatch, worker_database)
    class State:
        def get_sync(self, key):
            return None
        def set_sync(self, *args, **kwargs):
            return True
    monkeypatch.setattr(learning, "state", State())
    monkeypatch.setattr(repository, "state", State())
    monkeypatch.setenv("ADAPTIVE_MIN_OUTCOME_SAMPLES", "20")
    asset = ("AUDITRESEARCH_" + uuid4().hex[:12]).upper()
    await seed_research_outcomes(get_session, asset)
    result = await learning.AdaptiveLearningWorker().run_once()
    assert result["candidates"] == 1 and result["walk_forward_runs"] == 1
    retry = await learning.AdaptiveLearningWorker().run_once()
    assert retry["candidates"] == 0 and retry["duplicates_skipped"] == 1
    async with get_session() as session:
        row = (await session.execute(text("SELECT metadata,state,is_current FROM adaptive_asset_profiles WHERE asset=:asset"), {"asset": asset})).mappings().one()
        evidence = row["metadata"]["research_validation"]
        assert row["state"] == "SHADOW" and not row["is_current"]
        assert evidence["trial_counts"]["raw_trial_count"] == 1
        assert evidence["walk_forward"]["leakage_checks_passed"]
        assert not evidence["promotion_eligible"] and not evidence["integrity"]["passed"]
        assert evidence["multiple_testing"]["status"] == "UNVERIFIED"
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiment_results"))).scalar_one() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["objective_exception", "aborted_database_transaction"])
async def test_actual_failed_worker_keeps_immutable_terminal_evidence_and_skips_closed_trials(monkeypatch, worker_database, mode):
    from sqlalchemy.exc import DBAPIError
    from engine.adaptive import learning, repository
    sessions = use_database(monkeypatch, worker_database)
    cache = SimpleNamespace(get_sync=lambda _: None, set_sync=lambda *a, **kw: True)
    monkeypatch.setattr(learning, "state", cache)
    monkeypatch.setattr(repository, "state", cache)
    monkeypatch.setenv("ADAPTIVE_MIN_OUTCOME_SAMPLES", "20")
    await seed_research_outcomes(sessions, "AUDITFAILURE")
    original_complete = learning.complete_experiment
    if mode == "objective_exception":
        def failed_objective(*args, **kwargs):
            raise RuntimeError("sensitive diagnostic must not enter persisted failure evidence")
        monkeypatch.setattr(learning, "walk_forward_evaluate", failed_objective)
        expected_error = RuntimeError
    else:
        async def failed_persistence(session, experiment_id, result, **kwargs):
            if kwargs.get("status", "COMPLETED") == "COMPLETED":
                await session.execute(text("SELECT 1 / 0"))
            await original_complete(session, experiment_id, result, **kwargs)
        monkeypatch.setattr(learning, "complete_experiment", failed_persistence)
        expected_error = DBAPIError
    with pytest.raises(expected_error):
        await learning.AdaptiveLearningWorker().run_once()
    async with sessions() as session:
        evidence = (await session.execute(text("SELECT status,result,evidence_hash FROM research_experiment_results"))).mappings().one()
        assert evidence["status"] == "FAILED" and not evidence["result"]["promotion_eligible"]
        assert evidence["result"]["error_type"] == expected_error.__name__
        assert "sensitive" not in json.dumps(evidence["result"])
        assert (await session.execute(text("SELECT status FROM adaptive_optimisation_runs"))).scalar_one() == "FAILED"
        assert (await session.execute(text("SELECT COUNT(*) FROM adaptive_asset_profiles"))).scalar_one() == 0
    retry = await learning.AdaptiveLearningWorker().run_once()
    assert retry["candidates"] == 0 and retry["failed_trials_skipped"] == retry["terminal_trials_skipped"] == 1
    async with sessions() as session:
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiments"))).scalar_one() == 1
        assert (await session.execute(text("SELECT evidence_hash FROM research_experiment_results"))).scalar_one() == evidence["evidence_hash"]


@pytest.mark.asyncio
async def test_new_trial_with_an_existing_profile_is_rejected_instead_of_left_pending(monkeypatch, worker_database):
    from engine.adaptive import learning, repository
    sessions = use_database(monkeypatch, worker_database)
    cache = SimpleNamespace(get_sync=lambda _: None, set_sync=lambda *a, **kw: True)
    monkeypatch.setattr(learning, "state", cache)
    monkeypatch.setattr(repository, "state", cache)
    monkeypatch.setenv("ADAPTIVE_MIN_OUTCOME_SAMPLES", "20")
    await seed_research_outcomes(sessions, "AUDITDUPLICATE")
    monkeypatch.setenv("GITHUB_SHA", "1" * 40)
    assert (await learning.AdaptiveLearningWorker().run_once())["candidates"] == 1
    monkeypatch.setenv("GITHUB_SHA", "2" * 40)
    retry = await learning.AdaptiveLearningWorker().run_once()
    assert retry["candidates"] == 0 and retry["duplicates_skipped"] == 1
    async with sessions() as session:
        rows = (await session.execute(text("SELECT status,result FROM research_experiment_results"))).mappings().all()
        assert sorted(row["status"] for row in rows) == ["COMPLETED", "REJECTED"]
        rejected = next(row for row in rows if row["status"] == "REJECTED")
        assert rejected["result"]["reason"] == "existing_profile_fingerprint"
        assert not rejected["result"]["promotion_eligible"]
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiments"))).scalar_one() == 2
        assert (await session.execute(text("SELECT COUNT(*) FROM adaptive_asset_profiles"))).scalar_one() == 1


@pytest.mark.asyncio
async def test_failure_recording_outage_keeps_the_durable_pending_definition_and_original_error(monkeypatch, worker_database, caplog):
    from engine.adaptive import learning, repository
    sessions = use_database(monkeypatch, worker_database)
    cache = SimpleNamespace(get_sync=lambda _: None, set_sync=lambda *a, **kw: True)
    monkeypatch.setattr(learning, "state", cache)
    monkeypatch.setattr(repository, "state", cache)
    monkeypatch.setenv("ADAPTIVE_MIN_OUTCOME_SAMPLES", "20")
    await seed_research_outcomes(sessions, "AUDITRECORDINGOUTAGE")
    @asynccontextmanager
    async def unavailable_recording(**kwargs):
        if kwargs.get("label") == "adaptive.record_failure":
            raise ConnectionError("synthetic persistence outage")
        async with sessions() as session:
            yield session
    def failed_objective(*args, **kwargs):
        raise RuntimeError("original objective failure")
    monkeypatch.setattr(learning, "get_session", unavailable_recording)
    monkeypatch.setattr(learning, "walk_forward_evaluate", failed_objective)
    with pytest.raises(RuntimeError, match="original objective failure"):
        await learning.AdaptiveLearningWorker().run_once()
    async with sessions() as session:
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiments"))).scalar_one() == 1
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiment_results"))).scalar_one() == 0
    assert "failure_recording_failed" in caplog.text
    assert "synthetic persistence outage" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "wrong_columns", "wrong_relation", "unique", "expression", "partial", "included", "cancelled_build"])
async def test_actual_admission_rejects_missing_or_misidentified_health_indexes(monkeypatch, worker_database, fault):
    import db.session as db_session
    import railway_main
    from scripts import assert_database_schema as schema_gate
    from db.profile_health_schema import PROFILE_HEALTH_INDEX_SQL, profile_health_index_valid

    @asynccontextmanager
    async def sessions(**kwargs):
        async with worker_database() as session:
            yield session
    monkeypatch.setattr(db_session, "is_db_configured", lambda: True)
    monkeypatch.setattr(db_session, "get_session", sessions)
    url = worker_database.kw["bind"].url.set(drivername="postgresql").render_as_string(hide_password=False)
    monkeypatch.setattr(schema_gate, "_runtime_database_url", lambda: url)
    admission = await railway_main._database_readiness_check()
    async with worker_database() as session:
        index_metadata = dict((await session.execute(text(PROFILE_HEALTH_INDEX_SQL))).mappings().one())
    assert admission["ok"], {"admission": admission, "index": index_metadata}
    assert schema_gate.check_schema()["ok"]
    async with sessions() as session:
        await session.execute(text("DROP INDEX public.ix_adaptive_evidence_profile_signal"))
        if fault == "wrong_columns":
            await session.execute(text("CREATE INDEX ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (signal_id,profile_id)"))
        elif fault == "wrong_relation":
            await session.execute(text("CREATE INDEX ix_adaptive_evidence_profile_signal ON public.signals (signal_id,asset)"))
        elif fault == "unique":
            await session.execute(text("CREATE UNIQUE INDEX ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (profile_id,signal_id)"))
        elif fault == "expression":
            await session.execute(text("CREATE INDEX ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (lower(profile_id),signal_id)"))
        elif fault == "partial":
            await session.execute(text("CREATE INDEX ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (profile_id,signal_id) WHERE profile_id IS NOT NULL"))
        elif fault == "included":
            await session.execute(text("CREATE INDEX ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (profile_id,signal_id) INCLUDE (asset)"))
        await session.commit()
    if fault == "cancelled_build":
        # Create a genuine invalid index without editing system catalogues:
        # hold a writer lock, cancel the concurrent build after catalogue
        # creation, and release only these owned database connections.
        from sqlalchemy.exc import DBAPIError
        from importlib import import_module
        engine = worker_database.kw["bind"]
        async with engine.connect() as blocker, engine.connect() as build:
            await blocker.execute(text("LOCK TABLE public.adaptive_signal_evidence IN ROW EXCLUSIVE MODE"))
            build = await build.execution_options(isolation_level="AUTOCOMMIT")
            pid = (await build.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            operation = asyncio.create_task(build.execute(text(import_module("db.migrations.versions.0050_profile_health_index").CREATE_SQL)))
            try:
                for _ in range(100):
                    async with sessions() as session:
                        observed = (await session.execute(text(PROFILE_HEALTH_INDEX_SQL))).mappings().one_or_none()
                    if observed is not None and observed["indisvalid"] is False:
                        break
                    await asyncio.sleep(0.05)
                else:
                    pytest.fail("concurrent build did not expose an invalid index within the bounded wait")
                async with sessions() as session:
                    assert (await session.execute(text("SELECT pg_cancel_backend(:pid)"), {"pid": pid})).scalar_one()
                with pytest.raises(DBAPIError):
                    await asyncio.wait_for(operation, timeout=10)
            finally:
                await blocker.rollback()
                if not operation.done():
                    operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
    runtime = await railway_main._database_readiness_check()
    assert not runtime["ok"] and runtime["detail"] == "adaptive_profile_health_index_missing_or_invalid"
    assert "adaptive_profile_health_index" in schema_gate.check_schema()["missing"]
    async with sessions() as session:
        record = (await session.execute(text(PROFILE_HEALTH_INDEX_SQL))).mappings().one_or_none()
        assert not profile_health_index_valid(dict(record) if record is not None else None)
    # Exercise the real concurrent migration operation on retry, including
    # refusal to drop a correctly named index on the wrong keys/relation.
    from importlib import import_module
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    async def retry_index_build():
        async with worker_database.kw["bind"].connect() as connection:
            def retry(sync_connection):
                context = MigrationContext.configure(sync_connection)
                with context.begin_transaction(), Operations.context(context):
                    import_module("db.migrations.versions.0050_profile_health_index").upgrade()
            await connection.run_sync(retry)
    if fault in {"missing", "cancelled_build"}:
        await retry_index_build()
        await retry_index_build()
        assert (await railway_main._database_readiness_check())["ok"]
        assert schema_gate.check_schema()["ok"]
    else:
        with pytest.raises(RuntimeError, match="definition_mismatch"):
            await retry_index_build()
        async with sessions() as session:
            unchanged = (await session.execute(text(PROFILE_HEALTH_INDEX_SQL))).mappings().one()
            assert unchanged["columns"] == record["columns"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["paused", "disabled"])
@pytest.mark.parametrize("observations", ["degraded", "nonfinite"])
async def test_health_suspends_degradation_while_research_is_stopped(monkeypatch, worker_database, mode, observations):
    from db.models import Signal, Outcome, User, SignalDelivery, AdaptiveAssetProfile, AdaptiveSignalEvidence
    from engine.adaptive import learning, repository
    from utils.timeutils import now_utc_naive
    get_session = use_database(monkeypatch, worker_database)
    cache_invalidations = []

    class State:
        def get_sync(self, key):
            return "1" if mode == "paused" and key == "adaptive:optimisation:paused" else None
        def set_sync(self, *args, **kwargs):
            return True

    monkeypatch.setattr(learning, "state", State())
    monkeypatch.setattr(repository, "state", State())
    monkeypatch.setattr(repository, "invalidate_profile_cache", cache_invalidations.append)
    monkeypatch.setenv("ADAPTIVE_OPTIMISATION_ENABLED", "0" if mode == "disabled" else "1")
    asset, current, old = "AUDITHEALTH", "health-current", "health-old"
    start = now_utc_naive() - timedelta(days=5)
    async with get_session() as session:
        user = User(telegram_user_id=987654321)
        session.add(user)
        session.add_all([
            AdaptiveAssetProfile(profile_id=old, asset=asset, asset_class="crypto", version=1,
                                 state="APPROVED", is_current=False),
            AdaptiveAssetProfile(profile_id=current, asset=asset, asset_class="crypto", version=2,
                                 state="CANARY", is_current=True, rollback_profile_id=old)])
        await session.flush()
        for i in range(2 if observations == "nonfinite" else 35):
            signal_id = str(uuid4())
            session.add(Signal(signal_id=signal_id, asset=asset, asset_class="crypto", timeframe="1h", direction="long",
                               entry=100, stop_loss=90, take_profit="[110]", score=80, strength=0.8,
                               strategy_name="audit", strategy_group="trend", regime="trend", status="closed",
                               created_at=start + timedelta(hours=i)))
            await session.flush()
            session.add(Outcome(signal_id=signal_id, status="loss", r_multiple=float("nan") if observations == "nonfinite" else -1, provenance="delivered",
                                closed_at=start + timedelta(hours=i, minutes=30), performance_inclusion_status="eligible"))
            session.add(SignalDelivery(user_id=user.id, signal_id=signal_id, sent_ok=True, delivery_state="CONFIRMED"))
            session.add(AdaptiveSignalEvidence(signal_id=signal_id, asset=asset, timeframe="1h", strategy_id="audit",
                strategy_version="1", family="trend", direction="long", setup_type="audit", confidence=0.8,
                raw_score=80, profile_id=current, profile_version=2, duplicate_fingerprint=uuid4().hex))
        await session.commit()
    result = await learning.AdaptiveLearningWorker().run_once()
    assert result[mode] is True and result["drift"]["suspended_assets"] == [asset]
    assert cache_invalidations == [asset]
    async with get_session() as session:
        profiles = (await session.execute(text("SELECT profile_id,state,is_current FROM adaptive_asset_profiles"))).mappings().all()
        assert not any(row["is_current"] for row in profiles)
        assert next(row for row in profiles if row["profile_id"] == current)["state"] == "SUSPENDED"
        assert next(row for row in profiles if row["profile_id"] == old)["state"] == "APPROVED"
        assert (await session.execute(text("SELECT resolution FROM adaptive_drift_events"))).scalar_one() == "neutral_fallback_requires_revalidation"
        assert (await session.execute(text("SELECT COUNT(*) FROM research_experiments"))).scalar_one() == 0


@pytest.mark.asyncio
async def test_runtime_and_startup_admission_reject_every_disabled_research_guard(monkeypatch, worker_database):
    import db.session as db_session
    import railway_main
    from scripts import assert_database_schema as schema_gate

    @asynccontextmanager
    async def sessions(**kwargs):
        async with worker_database() as session:
            yield session

    monkeypatch.setattr(db_session, "is_db_configured", lambda: True)
    monkeypatch.setattr(db_session, "get_session", sessions)
    url = worker_database.kw["bind"].url.set(drivername="postgresql").render_as_string(hide_password=False)
    monkeypatch.setattr(schema_gate, "_runtime_database_url", lambda: url)
    assert (await railway_main._database_readiness_check())["ok"]
    assert schema_gate.check_schema()["ok"]

    for table in ("research_hypotheses", "research_experiments", "research_experiment_results"):
        for suffix in ("immutable", "no_truncate"):
            guard = f"{table}_{suffix}"
            async with worker_database() as session:
                await session.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER {guard}"))
                await session.commit()
            try:
                runtime = await railway_main._database_readiness_check()
                assert not runtime["ok"]
                assert runtime["detail"] == "research_evidence_immutability_guards_missing"
                startup = schema_gate.check_schema()
                assert not startup["ok"]
                assert "research_append_only_triggers" in startup["missing"]
            finally:
                async with worker_database() as session:
                    await session.execute(text(f"ALTER TABLE public.{table} ENABLE TRIGGER {guard}"))
                    await session.commit()
    assert (await railway_main._database_readiness_check())["ok"]
    assert schema_gate.check_schema()["ok"]


@pytest.mark.asyncio
async def test_same_named_guard_on_the_wrong_relation_cannot_pass_admission(monkeypatch, worker_database):
    import db.session as db_session
    import railway_main
    from scripts import assert_database_schema as schema_gate

    @asynccontextmanager
    async def sessions(**kwargs):
        async with worker_database() as session:
            yield session

    monkeypatch.setattr(db_session, "is_db_configured", lambda: True)
    monkeypatch.setattr(db_session, "get_session", sessions)
    url = worker_database.kw["bind"].url.set(drivername="postgresql").render_as_string(hide_password=False)
    monkeypatch.setattr(schema_gate, "_runtime_database_url", lambda: url)
    async with worker_database() as session:
        await session.execute(text("DROP TRIGGER research_hypotheses_immutable ON public.research_hypotheses"))
        await session.execute(text("""CREATE TRIGGER research_hypotheses_immutable
            BEFORE UPDATE OR DELETE ON public.research_experiments
            FOR EACH ROW EXECUTE FUNCTION public.reject_research_evidence_mutation()"""))
        await session.commit()
    assert (await railway_main._database_readiness_check())["detail"] == "research_evidence_immutability_guards_missing"
    assert "research_append_only_triggers" in schema_gate.check_schema()["missing"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["suspend", "rollback"])
async def test_inflight_profile_publication_cannot_undo_deactivation(monkeypatch, worker_database, action):
    from db.models import AdaptiveAssetProfile
    from engine.adaptive import repository, profiles
    from signalrank_telegram import adaptive_commands as commands

    async with worker_database() as session:
        session.add_all([
            AdaptiveAssetProfile(profile_id="cache-old", asset="AUDITCACHE", asset_class="crypto", version=1,
                                 state="APPROVED", is_current=False),
            AdaptiveAssetProfile(profile_id="cache-current", asset="AUDITCACHE", asset_class="crypto", version=2,
                                 state="CANARY", is_current=True, rollback_profile_id="cache-old")])
        await session.commit()
    read = asyncio.Event()
    release = asyncio.Event()
    contender = asyncio.Event()
    values = {}
    fake_state = SimpleNamespace(get_sync=values.get,
        set_sync=lambda key, value, **kwargs: values.__setitem__(key, value))

    class SessionProxy:
        def __init__(self, session, label):
            self.session, self.label = session, label
        def __getattr__(self, name):
            return getattr(self.session, name)
        async def execute(self, statement, parameters=None):
            sql = str(statement)
            if self.label.startswith("adaptive.command.") and "pg_advisory_xact_lock" in sql:
                contender.set()
            result = await self.session.execute(statement, parameters or {})
            if self.label == "adaptive.publish_profiles" and "FROM adaptive_asset_profiles" in sql:
                read.set()
                await release.wait()
            return result

    @asynccontextmanager
    async def sessions(**kwargs):
        async with worker_database() as session:
            yield SessionProxy(session, kwargs.get("label", ""))

    monkeypatch.setattr(repository, "get_session", sessions)
    monkeypatch.setattr(commands, "get_session", sessions)
    monkeypatch.setattr(repository, "state", fake_state)
    monkeypatch.setattr(profiles, "state", fake_state)
    monkeypatch.setattr(commands, "_require_owner", AsyncMock(return_value=True))
    monkeypatch.setattr(commands, "_reply", AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42))
    command = commands.adaptive_suspend_command if action == "suspend" else commands.adaptive_rollback_command
    context = SimpleNamespace(args=["cache-current" if action == "suspend" else "AUDITCACHE"])
    publisher = asyncio.create_task(repository.publish_approved_profiles())
    deactivation = None
    try:
        await asyncio.wait_for(read.wait(), timeout=5)
        deactivation = asyncio.create_task(command(update, context))
        await asyncio.wait_for(contender.wait(), timeout=5)
        done, _ = await asyncio.wait({deactivation}, timeout=0.05)
        assert not done, "deactivation must serialize with the in-flight publisher"
        release.set()
        await asyncio.wait_for(asyncio.gather(publisher, deactivation), timeout=10)
        cached = json.loads(values["adaptive:profile:approved:AUDITCACHE"])
        assert cached["state"] == "SUSPENDED"
        assert profiles.ProfileResolver().resolve("AUDITCACHE", "crypto").metadata["neutral_fallback"]
        async with worker_database() as session:
            assert not (await session.execute(text("SELECT EXISTS(SELECT 1 FROM adaptive_asset_profiles WHERE is_current)"))).scalar_one()
            assert (await session.execute(text("SELECT state FROM adaptive_asset_profiles WHERE profile_id='cache-old'"))).scalar_one() == "APPROVED"
    finally:
        release.set()
        for task in (publisher, deactivation):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (publisher, deactivation) if task is not None), return_exceptions=True)
