from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

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
async def test_actual_worker_persists_a_nonpromotable_candidate_and_reuses_trial(monkeypatch, worker_database):
    from db.models import Signal, Outcome
    from utils.timeutils import now_utc_naive
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
    start = now_utc_naive() - timedelta(days=10)
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0049_research_trial_ledger"
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
@pytest.mark.parametrize("mode", ["paused", "disabled"])
async def test_health_suspends_degradation_while_research_is_stopped(monkeypatch, worker_database, mode):
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
        for i in range(35):
            signal_id = str(uuid4())
            session.add(Signal(signal_id=signal_id, asset=asset, asset_class="crypto", timeframe="1h", direction="long",
                               entry=100, stop_loss=90, take_profit="[110]", score=80, strength=0.8,
                               strategy_name="audit", strategy_group="trend", regime="trend", status="closed",
                               created_at=start + timedelta(hours=i)))
            await session.flush()
            session.add(Outcome(signal_id=signal_id, status="loss", r_multiple=-1, provenance="delivered",
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
