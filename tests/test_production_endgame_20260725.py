from __future__ import annotations

import asyncio
import inspect
import urllib.error

from sqlalchemy.dialects import postgresql


def test_offline_bootstrap_is_never_allowed_on_railway(monkeypatch):
    from ml import train_model

    for name in (
        "APP_ENV",
        "ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_NAME",
        "ML_OFFLINE_BOOTSTRAP_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("APP_ENV", "development")
    assert train_model._offline_bootstrap_allowed() is True

    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "signalrankai-analytics")
    monkeypatch.setenv("ML_OFFLINE_BOOTSTRAP_ENABLED", "1")
    assert train_model._is_production_runtime() is True
    assert train_model._offline_bootstrap_allowed() is False


def test_worker_does_not_own_analytics_in_monolith(monkeypatch):
    from worker import worker

    monkeypatch.setenv("RUN_MODE", "all")
    monkeypatch.delenv("ALLOW_ANALYTICS_IN_WORKER", raising=False)
    monkeypatch.delenv("ALLOW_ML_TRAIN_IN_MONOLITH", raising=False)
    assert worker._analytics_work_allowed_in_worker() is False

    monkeypatch.setenv("RUN_MODE", "analytics")
    assert worker._analytics_work_allowed_in_worker() is True

    monkeypatch.setenv("RUN_MODE", "all")
    monkeypatch.setenv("ALLOW_ANALYTICS_IN_WORKER", "1")
    assert worker._analytics_work_allowed_in_worker() is True


def test_portfolio_exposure_query_requires_delivery_proof(monkeypatch):
    from engine.correlation_filter import PortfolioExposureManager

    monkeypatch.setenv("PORTFOLIO_EXPOSURE_REQUIRE_DELIVERED", "1")

    class _Result:
        @staticmethod
        def fetchall():
            return []

    class _Session:
        query = None

        async def execute(self, query):
            self.query = query
            return _Result()

    session = _Session()
    allowed = asyncio.run(
        PortfolioExposureManager()._check_exposure(session, "crypto", "short")
    )
    assert allowed is True
    sql = str(
        session.query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "exists" in sql
    assert "signal_deliveries" in sql
    assert "sent_ok is true" in sql
    assert "telegram_chat_id is not null" in sql
    assert "telegram_message_id is not null" in sql
    assert "delivery_confirmed_at" in sql
    assert "delivered_at_utc" in sql
    assert "expires_at" in sql
    assert "outcomes" in sql
    assert "signal_lifecycles" in sql
    assert "terminal_event_type is not null" in sql
    assert "breakeven_stop" in sql
    assert "closed_at is not null" in sql
    assert "tp3" in sql
    assert "missed_entry" in sql
    assert "tp1" not in sql


def test_engine_open_count_excludes_terminal_outcomes():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "terminal_outcome_open_count" in source
    assert "open_proof_cutoff" in source
    assert "DELIVERY_UNRESOLVED_BLOCK_HOURS" in source
    assert "terminal_lifecycle_open_count" in source
    assert "_OpenLifecycle.terminal_event_type.is_not(None)" in source
    assert "_OpenOutcome.closed_at.is_not(None)" in source
    assert '"tp3"' in source
    assert '"missed_entry"' in source


def test_redis_empty_reconciliation_cannot_mass_expire_signals():
    from engine import core

    source = inspect.getsource(core.main_loop)
    assert "redis active trades empty; retaining %s proof-backed DB open signals" in source
    assert "redis active trades empty; expired %s stale DB open signals" not in source


def test_engine_pulse_partial_fanout_does_not_fail_engine_health():
    from pathlib import Path

    source = Path("engine/admin_pulse.py").read_text(encoding="utf-8")
    assert "notification_reachable = sent > 0" in source
    assert 'sent == len(recipients)' not in source
    assert "recipients_attempted=len(recipients)" in source
    assert "partial Telegram fanout" in source


def test_segment_quarantine_uses_delivery_proof():
    from engine import core

    source = inspect.getsource(core._segment_quarantine_gate)
    assert "SEGMENT_QUARANTINE_REQUIRE_DELIVERED" in source
    assert "FROM signal_deliveries sd" in source
    assert "sd.sent_ok IS TRUE" in source
    assert "SEGMENT_QUARANTINE_MIN_TRADES\", 30" in source


def test_gemini_429_opens_process_circuit(monkeypatch):
    from engine import core

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_SIGNAL_REVIEW_ENABLED", "1")
    monkeypatch.setenv("GEMINI_SIGNAL_REVIEW_CIRCUIT_BREAKER_ENABLED", "1")
    monkeypatch.setenv("GEMINI_RATE_LIMIT_COOLDOWN_SECONDS", "900")
    monkeypatch.setenv("QUALITY_MIN_LOCAL_AI_SCORE", "1")

    core._GEMINI_RATE_LIMIT_UNTIL_MONO = 0.0
    core._GEMINI_REVIEW_WINDOW_STARTED_MONO = 0.0
    core._GEMINI_REVIEW_WINDOW_CALLS = 0
    calls = {"count": 0}

    def _rate_limited(*args, **kwargs):
        calls["count"] += 1
        raise urllib.error.HTTPError(
            url="https://example.invalid",
            code=429,
            msg="rate limited",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(core.urllib.request, "urlopen", _rate_limited)
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": [102.0],
        "score": 95.0,
        "rr_ratio": 2.0,
    }
    candles = [{"close": 100.0}] * 100

    first = asyncio.run(core._gemini_review_signal(signal, candles, None))
    second = asyncio.run(core._gemini_review_signal(signal, candles, None))

    assert calls["count"] == 1
    assert "rate_limited_degraded" in first[2]
    assert "rate_limited_circuit_open" in second[2]


def test_gemini_404_opens_provider_config_circuit(monkeypatch):
    from engine import core

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_SIGNAL_REVIEW_ENABLED", "1")
    monkeypatch.setenv("GEMINI_SIGNAL_REVIEW_CIRCUIT_BREAKER_ENABLED", "1")
    monkeypatch.setenv("GEMINI_CONFIG_ERROR_COOLDOWN_SECONDS", "3600")
    monkeypatch.setenv("QUALITY_MIN_LOCAL_AI_SCORE", "1")

    core._GEMINI_RATE_LIMIT_UNTIL_MONO = 0.0
    core._GEMINI_CIRCUIT_REASON = ""
    core._GEMINI_REVIEW_WINDOW_STARTED_MONO = 0.0
    core._GEMINI_REVIEW_WINDOW_CALLS = 0
    calls = {"count": 0}

    def _missing_model(*args, **kwargs):
        calls["count"] += 1
        raise urllib.error.HTTPError(
            url="https://example.invalid",
            code=404,
            msg="model not found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(core.urllib.request, "urlopen", _missing_model)
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": [102.0],
        "score": 95.0,
        "rr_ratio": 2.0,
    }
    candles = [{"close": 100.0}] * 100

    first = asyncio.run(core._gemini_review_signal(signal, candles, None))
    second = asyncio.run(core._gemini_review_signal(signal, candles, None))

    assert calls["count"] == 1
    assert "provider_http_404_degraded" in first[2]
    assert "provider_http_404_circuit_open" in second[2]


def test_current_gemini_review_request_avoids_legacy_sampling_knobs():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    review = source[source.index("async def _gemini_review_signal"):source.index("def _log_decision")]
    assert '"generationConfig": {"maxOutputTokens": 160}' in review
    assert '"temperature": 0.1' not in review
    assert "gemini review provider_error status=" in review


def test_metaapi_discovery_uses_canonical_account_aliases():
    from pathlib import Path

    source = Path("data/pair_discovery.py").read_text(encoding="utf-8")
    start = source.index("def _metaapi_symbols")
    end = source.index("def get_trending_crypto_pairs", start)
    block = source[start:end]
    assert 'os.getenv("META_API_MARKET_DATA_ACCOUNT_ID")' in block
    assert 'os.getenv("META_API_ACCOUNT_ID")' in block
    assert 'os.getenv("METAAPI_ACCOUNT_ID")' in block
    assert 'os.getenv("META_API_TOKEN")' in block
    assert 'os.getenv("METAAPI_TOKEN")' in block


def test_staging_quality_advisory_requires_nonproduction_and_no_live_execution():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    helper = source[source.index("def _staging_quality_advisory_enabled"):source.index("def _append_staging_advisory")]
    assert 'environment in {"production", "prod"}' in helper
    assert 'PUBLIC_TESTING_MODE' in helper
    assert 'STAGING_QUALITY_GATES_ADVISORY' in helper
    assert 'REAL_EXECUTION_ENABLED' in helper
    assert 'AUTO_EXECUTION_ENABLED' in helper
    assert 'COPY_TRADE_ENABLED' in helper
    assert 'HYPERLIQUID_MAINNET_EXECUTION_ENABLED' in helper
    assert 'FULL_SYSTEM_STAGING_TEST_ACTIVE' not in helper


def test_worker_startup_db_jobs_use_bounded_configurable_waits():
    from pathlib import Path

    source = Path("worker/worker.py").read_text(encoding="utf-8")
    assert "WORKER_BOOTSTRAP_DB_TIMEOUT_SECONDS" in source
    assert "INSTRUMENT_DISCOVERY_DB_TIMEOUT_SECONDS" in source
    assert '_env_float("WORKER_BOOTSTRAP_DB_TIMEOUT_SECONDS", 60.0' in source
    assert '_env_float("INSTRUMENT_DISCOVERY_DB_TIMEOUT_SECONDS", 60.0' in source


def test_delivery_worker_does_not_own_learning_retention():
    from pathlib import Path

    source = Path("worker/worker.py").read_text(encoding="utf-8")
    assert "LearningHistoryRetention started" not in source
    assert '"learning_history_retention"' not in source


def test_analytics_role_owns_continuous_improvement_scheduler():
    import inspect
    from runtime import analytics

    source = inspect.getsource(analytics.run_async)
    assert "CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED" in source
    assert "continuous_improvement_loop" in source
    assert "continuous-improvement-review" in source
    assert "LEARNING_HISTORY_RETENTION_ENABLED" in source
    assert "learning_history_maintenance_loop" in source
    assert "learning-history-retention" in source


def test_production_runtime_rejects_public_testing_mode():
    import ast
    import os
    from pathlib import Path

    source = Path("railway_main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_validate_production_runtime_contract"
    )
    module = ast.Module(body=[fn], type_ignores=[])
    namespace = {"os": os}
    exec(compile(module, "railway_main.py", "exec"), namespace)

    previous = {
        key: os.environ.get(key)
        for key in (
            "RAILWAY_ENVIRONMENT_NAME",
            "PUBLIC_TESTING_MODE",
            "ALLOW_PUBLIC_TESTING_IN_PRODUCTION",
        )
    }
    try:
        os.environ["RAILWAY_ENVIRONMENT_NAME"] = "production"
        os.environ["PUBLIC_TESTING_MODE"] = "1"
        os.environ.pop("ALLOW_PUBLIC_TESTING_IN_PRODUCTION", None)
        try:
            namespace["_validate_production_runtime_contract"]()
        except RuntimeError:
            pass
        else:
            raise AssertionError("production test mode was not rejected")

        os.environ["PUBLIC_TESTING_MODE"] = "0"
        namespace["_validate_production_runtime_contract"]()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_canonical_migration_head_is_active_guard_reconcile():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0038_account_security_product"]


def test_engine_metadata_reads_wait_boundedly_under_db_contention():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    for label in (
        "engine.profile_demand",
        "engine.managed_assets",
        "engine.database_universe",
    ):
        pos = source.index(f'label="{label}"')
        window = source[max(0, pos - 220): pos + 360]
        assert "priority=\"background\"" in window
        assert "drop_if_busy=False" in window
        assert "ENGINE_METADATA_DB_TIMEOUT_SECONDS" in window


def test_engine_required_metadata_uses_protected_lane_and_outer_timeout_exceeds_db_wait():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    for label in ("engine.profile_demand", "engine.managed_assets", "engine.database_universe"):
        idx = source.index(f'label="{label}"')
        block = source[max(0, idx - 500):idx + 1200]
        assert 'priority="critical"' in block
        assert "drop_if_busy=False" in block

    assert 'PROFILE_DEMAND_LOAD_TIMEOUT_SECONDS", "12"' in source
    assert 'ENGINE_MANAGED_ASSETS_TIMEOUT_SECONDS", "12"' in source
    assert 'ENGINE_DATABASE_UNIVERSE_TIMEOUT_SECONDS", "12"' in source
    assert '_env_float("ENGINE_METADATA_DB_TIMEOUT_SECONDS", 10.0) + 2.0' in source
