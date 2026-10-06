"""Real PostgreSQL evidence: append-only history, lineage and crash persistence."""
from importlib import import_module
from contextlib import asynccontextmanager
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import DBAPIError

from engine.adaptive.research_ledger import (
    register_hypothesis, start_experiment, complete_experiment, trial_counts, research_snapshot, canonical_json,
    run_recorded_search,
)


@pytest_asyncio.fixture
async def research_database():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("isolated PostgreSQL required")
        pytest.skip("isolated PostgreSQL not configured")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql" and parsed.host in {"127.0.0.1", "localhost"}
    assert os.getenv("APP_ENV") == "test"
    assert "test" in parsed.database or parsed.database == "signalrank_master_audit"
    schema = "research_test_" + uuid4().hex[:16]
    admin = create_async_engine(parsed.set(drivername="postgresql+asyncpg"))
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(parsed.set(drivername="postgresql+asyncpg"),
                                 connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE adaptive_dataset_versions(dataset_version VARCHAR(128) PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE adaptive_feature_versions(feature_version VARCHAR(128) PRIMARY KEY)"))
            await connection.execute(text("INSERT INTO adaptive_dataset_versions VALUES('fixture-dataset')"))
            await connection.execute(text("INSERT INTO adaptive_feature_versions VALUES('fixture-feature')"))
            def migrate(sync_connection):
                from alembic.migration import MigrationContext
                from alembic.operations import Operations
                with Operations.context(MigrationContext.configure(sync_connection)):
                    import_module("db.migrations.versions.0049_research_trial_ledger").upgrade()
            await connection.run_sync(migrate)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def specification(parameter=1):
    return {"parameter_set": {"stop_multiplier": parameter}, "dataset_version": "fixture-dataset",
            "feature_version": "fixture-feature", "label_version": "fixture-v1", "execution_model_version": "v1",
            "risk_model_version": "v1", "code_commit": "fixture-commit", "random_seed": 41,
            "asset_scope": ["BTCUSDT"], "timeframe_scope": ["1h"], "regime_scope": ["trend"]}


async def hypothesis(session, parent=None):
    return await register_hypothesis(session, trial_family="unchanged-lineage" if not parent else "renamed-family",
        spec={"mechanism_status": "mechanism_unproven", "description": "changed" if parent else "initial"},
        code_commit="fixture-commit", created_by="test", parent_hypothesis_id=parent)


@pytest.mark.asyncio
async def test_retry_and_strategy_renaming_preserve_lineage_counts(research_database):
    async with research_database() as session:
        first = await hypothesis(session)
        original = await start_experiment(session, hypothesis_id=first, strategy_id="original", strategy_version="1", specification=specification())
        renamed = await start_experiment(session, hypothesis_id=first, strategy_id="renamed", strategy_version="1", specification=specification())
        assert original == renamed
        child = await hypothesis(session, first)
        variant = await start_experiment(session, hypothesis_id=child, strategy_id="renamed", strategy_version="2",
                                        specification=specification(2), parent_experiment_id=original)
        await complete_experiment(session, variant, {"test": "negative_result"}, status="REJECTED")
        counts = await trial_counts(session, child)
        assert counts["raw_trial_count"] == 2 and counts["terminal_trial_count"] == 1
        assert counts["effective_trial_count"] == 2
        assert not counts["pre_ledger_trial_history_verified"]
        snapshot = await research_snapshot(session, asset="BTCUSDT")
        assert len(snapshot["experiments"]) == 2
        assert await research_snapshot(session, asset="AAPL") == {
            "experiments": [], "families": snapshot["families"],
            "historical_coverage": "since_ledger_introduction", "automatic_live_promotion": False}


@pytest.mark.asyncio
async def test_committed_trial_survives_failed_research_transaction(research_database):
    async with research_database() as session:
        root = await hypothesis(session)
        experiment = await start_experiment(session, hypothesis_id=root, strategy_id="candidate", strategy_version="1", specification=specification())
        await session.commit()
    async with research_database() as session:
        await complete_experiment(session, experiment, {"metric": 0.2})
        await session.rollback()  # Simulate evaluation crash before result commit.
    async with research_database() as session:
        counts = await trial_counts(session, root)
        assert counts["raw_trial_count"] == 1 and counts["terminal_trial_count"] == 0
        assert (await research_snapshot(session))["experiments"][0]["status"] is None


@pytest.mark.asyncio
async def test_terminal_results_are_idempotent_but_conflicting_evidence_is_rejected(research_database):
    async with research_database() as session:
        root = await hypothesis(session)
        experiment = await start_experiment(session, hypothesis_id=root, strategy_id="candidate", strategy_version="1", specification=specification())
        await complete_experiment(session, experiment, {"metric": 0.2})
        await complete_experiment(session, experiment, {"metric": 0.2})
        with pytest.raises(ValueError, match="conflicting_immutable"):
            await complete_experiment(session, experiment, {"metric": 0.3})


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["research_hypotheses", "research_experiments", "research_experiment_results"])
@pytest.mark.parametrize("operation", ["DELETE FROM", "TRUNCATE"])
async def test_database_rejects_direct_evidence_deletion(research_database, table, operation):
    async with research_database() as session:
        root = await hypothesis(session)
        experiment = await start_experiment(session, hypothesis_id=root, strategy_id="candidate", strategy_version="1", specification=specification())
        await complete_experiment(session, experiment, {"metric": 0.2})
        await session.commit()
        with pytest.raises(DBAPIError, match="append_only"):
            async with session.begin_nested():
                await session.execute(text(f"{operation} {table}" + (" CASCADE" if operation == "TRUNCATE" else "")))


def test_evidence_rejects_nonfinite_numbers_and_secret_fields():
    with pytest.raises(ValueError):
        canonical_json({"result": float("nan")})
    with pytest.raises(ValueError, match="secret_field"):
        canonical_json({"metadata": {"api_key": "must-not-persist"}})


def test_rollback_cannot_erase_trial_history():
    with pytest.raises(RuntimeError, match="preserved_evidence"):
        import_module("db.migrations.versions.0049_research_trial_ledger").downgrade()


@pytest.mark.asyncio
@pytest.mark.parametrize("objective_fails", [False, True])
async def test_grid_optimizer_commits_each_trial_before_evaluation(research_database, objective_fails, monkeypatch):
    from engine.backtest import OptimizationEngine
    # The hermetic unit suite inlines to_thread globally. This integration
    # exercises the real worker-thread -> PostgreSQL event-loop bridge.
    from asyncio.threads import to_thread
    monkeypatch.setattr(asyncio, "to_thread", to_thread)
    loop = asyncio.get_running_loop()
    async with research_database() as session:
        root = await hypothesis(session)
        await session.commit()

    @asynccontextmanager
    async def sessions(**kwargs):
        async with research_database() as session:
            yield session

    async def count_committed():
        async with research_database() as session:
            return await trial_counts(session, root)

    observations = []
    def objective(parameters):
        counts = asyncio.run_coroutine_threadsafe(count_committed(), loop).result(timeout=10)
        observations.append(counts)
        assert counts["raw_trial_count"] == len(observations)
        assert counts["terminal_trial_count"] == len(observations) - 1
        if objective_fails:
            raise ValueError("evaluation_failed")
        return {"expectancy_r": parameters["stop_multiplier"] / 10}

    search = lambda recorder: OptimizationEngine().optimize_parameters(
        objective, {"stop_multiplier": [1, 2]}, record_trial=recorder)
    kwargs = dict(hypothesis_id=root, strategy_id="grid-test", strategy_version="1",
                  specification=specification(), session_factory=sessions)
    if objective_fails:
        with pytest.raises(ValueError, match="evaluation_failed"):
            await run_recorded_search(search, **kwargs)
    else:
        result = await run_recorded_search(search, **kwargs)
        assert result["trial_counts"]["raw_trial_count"] == 2
        assert result["result"]["best_params"] == {"stop_multiplier": 2}
        assert not result["automatic_live_promotion"]
    async with research_database() as session:
        snapshot = await research_snapshot(session)
        assert len(snapshot["experiments"]) == (1 if objective_fails else 2)
        assert all(row["status"] == ("FAILED" if objective_fails else "COMPLETED") for row in snapshot["experiments"])
        assert all(not row["result"]["promotion_eligible"] for row in snapshot["experiments"])


@pytest.mark.asyncio
async def test_database_rejects_lineage_reset_even_for_direct_sql(research_database):
    async with research_database() as session:
        root = await hypothesis(session)
        await session.commit()
        with pytest.raises(DBAPIError, match="research_hypothesis_lineage_mismatch"):
            async with session.begin_nested():
                await session.execute(text("""INSERT INTO research_hypotheses(
                    hypothesis_id,parent_hypothesis_id,trial_family,version,spec,content_hash,created_by,code_commit)
                    VALUES(:id,:parent,'renamed-lineage',2,'{}',:id,'fixture','fixture')"""),
                    {"id": "f" * 64, "parent": root})
