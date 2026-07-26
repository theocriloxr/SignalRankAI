from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects import postgresql


def test_portfolio_exposure_binds_naive_utc(monkeypatch):
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
    assert asyncio.run(
        PortfolioExposureManager()._check_exposure(session, "crypto", "long")
    ) is True

    compiled = session.query.compile(dialect=postgresql.dialect())
    datetimes = [value for value in compiled.params.values() if isinstance(value, datetime)]
    assert datetimes, "exposure query must bind an expiry cutoff"
    assert all(value.tzinfo is None for value in datetimes)


def test_portfolio_exposure_failure_mode_is_execution_aware(monkeypatch):
    from core.redis_state import state
    from engine.correlation_filter import PortfolioExposureManager

    monkeypatch.setattr(state, "get_active_trades_sync", lambda: {})
    monkeypatch.delenv("PORTFOLIO_EXPOSURE_FAIL_OPEN", raising=False)
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "0")
    monkeypatch.setenv("COPY_TRADE_ENABLED", "0")
    assert PortfolioExposureManager()._fallback_exposure_allowed(
        "crypto", "long", RuntimeError("db unavailable")
    ) is True

    monkeypatch.setenv("AUTO_TRADE_ENABLED", "1")
    assert PortfolioExposureManager()._fallback_exposure_allowed(
        "crypto", "long", RuntimeError("db unavailable")
    ) is False


def test_cryptocompare_candle_builder_accepts_ticker_updates():
    from data.ws_ingest import _CryptoCompareCandleBuilder

    builder = _CryptoCompareCandleBuilder(intervals=["1m", "5m"])
    first = builder.update(
        symbol="BTCUSDT",
        price=100.0,
        volume=0.0,
        event_time_ms=1_800_000,
    )
    second = builder.update(
        symbol="BTCUSDT",
        price=101.0,
        volume=0.0,
        event_time_ms=1_830_000,
    )
    assert {row["timeframe"] for row in first} == {"1m", "5m"}
    assert all(row["is_final"] is False for row in first)
    assert all(row["close"] == 101.0 for row in second)


def test_ws_ingestor_no_longer_leaks_cancelled_error():
    source = Path("data/ws_ingest.py").read_text(encoding="utf-8")
    assert "contextlib.suppress(asyncio.CancelledError, Exception)" in source
    assert 'priority=DBPriority.BACKGROUND' in source
    assert 'event_type in {"tick", "trade"}' in source
    assert 'event_type == "__feeder_error__"' in source


def test_rejection_telemetry_is_batched(monkeypatch):
    import engine.signal_deduplicator as module

    with module._REJECTION_SPOOL_LOCK:
        module._REJECTION_SPOOL.clear()
    module._REJECTION_LAST_FLUSH_MONO = module.time.monotonic()

    monkeypatch.setenv("REJECTION_DB_BATCH_SIZE", "3")
    monkeypatch.setenv("REJECTION_DB_FLUSH_SECONDS", "999")
    monkeypatch.setenv("REJECTION_DB_TIMEOUT_SECONDS", "0.5")

    committed: list[object] = []
    commits = {"count": 0}

    class _Session:
        def add_all(self, rows):
            committed.extend(rows)

        async def commit(self):
            commits["count"] += 1

    @asynccontextmanager
    async def _session(**kwargs):
        assert kwargs["label"] == "rejection_batch_write"
        yield _Session()

    monkeypatch.setattr(module, "get_session", _session)
    tracker = module.MLRejectionTracker()

    async def _run():
        for index in range(3):
            await tracker.persist_rejection(
                asset="BTCUSDT",
                timeframe="5m",
                direction="long",
                entry_price=100 + index,
                stop_loss=99,
                take_profit_levels=[102],
                ml_probability=0.7,
                rejection_reason="quality",
                features={"index": index},
            )

    asyncio.run(_run())
    assert commits["count"] == 1
    assert len(committed) == 3
    assert tracker.pending_rejection_count() == 0



def test_sparse_rejection_telemetry_gets_delayed_flush(monkeypatch):
    import engine.signal_deduplicator as module

    with module._REJECTION_SPOOL_LOCK:
        module._REJECTION_SPOOL.clear()
    module._REJECTION_LAST_FLUSH_MONO = module.time.monotonic()
    module._REJECTION_FLUSH_TASK = None

    monkeypatch.setenv("REJECTION_DB_BATCH_SIZE", "50")
    monkeypatch.setenv("REJECTION_DB_FLUSH_SECONDS", "0.01")

    commits = {"count": 0}

    class _Session:
        def add_all(self, rows):
            assert len(rows) == 1

        async def commit(self):
            commits["count"] += 1

    @asynccontextmanager
    async def _session(**kwargs):
        yield _Session()

    monkeypatch.setattr(module, "get_session", _session)
    tracker = module.MLRejectionTracker()

    async def _run():
        await tracker.persist_rejection(
            asset="BTCUSDT",
            timeframe="5m",
            direction="long",
            entry_price=100,
            stop_loss=99,
            take_profit_levels=[102],
            ml_probability=0.7,
            rejection_reason="quality",
            features={},
        )
        assert commits["count"] == 0
        await asyncio.sleep(0.2)

    asyncio.run(_run())
    assert commits["count"] == 1
    assert tracker.pending_rejection_count() == 0

def test_pair_discovery_has_no_default_import_time_network_thread():
    source = Path("data/pair_discovery.py").read_text(encoding="utf-8")
    assert 'ASSET_UNIVERSE_BACKGROUND_REFRESH_ENABLED", "0"' in source
    assert "def start_asset_universe_refresh_thread" in source


def test_waitlist_scheduler_uses_lightweight_canonical_module():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    assert "from services.waitlist_jobs import" in source
    assert 'importlib.import_module("web.app")' not in source


def test_free_distribution_deferral_is_not_logged_as_error():
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    marker = "[free_distribution] deferred by DB admission controller"
    assert marker in source
    assert 'isinstance(e, DatabaseWorkDeferred)' in source


def test_macro_yfinance_aliases_are_present():
    from data.market_data import format_ticker

    assert format_ticker("DXY", "yfinance") == "DX-Y.NYB"
    assert format_ticker("VIX", "yfinance") == "^VIX"
    assert format_ticker("US10Y", "yfinance") == "^TNX"
    assert format_ticker("US02Y", "yfinance") == "2YY=F"


def test_ml_archive_isolated_to_analytics_role():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    assert "def _ml_archive_backfill_enabled" in source
    assert 'run_mode in {"analytics", "ml", "learning"}' in source
    assert 'priority=DBPriority.ANALYTICS' in source
    assert 'ML_ARCHIVE_BACKFILL_ENABLED' in source


def test_waitlist_jobs_are_background_and_timezone_safe():
    source = Path("web/app.py").read_text(encoding="utf-8")
    assert 'label="waitlist_capacity"' in source
    assert 'label="waitlist_expiry"' in source
    assert source.count("priority=DBPriority.BACKGROUND") >= 2
    waitlist_tail = source[source.index("async def _check_waitlist_capacity_job"):]
    assert "datetime.utcnow()" not in waitlist_tail
    assert "now_utc_naive()" in waitlist_tail


def test_threshold_optimizer_imports_without_utcnow_fallback():
    source = Path("engine/threshold_optimizer.py").read_text(encoding="utf-8")
    assert "from utils.timeutils import now_utc_naive" in source
    assert "datetime.utcnow" not in source


def test_fast_monolith_profile_keeps_learning_and_ws_off():
    source = Path("deploy/railway_roles/monolith_safe.env").read_text(encoding="utf-8")
    required = {
        "PUBLIC_TESTING_MODE=0",
        "CRYPTO_ONLY_MODE=1",
        "WS_INGEST_ENABLED=0",
        "ML_TRAIN_ENABLED=0",
        "ML_OFFLINE_BOOTSTRAP_ENABLED=0",
        "ML_ARCHIVE_BACKFILL_ENABLED=0",
        "FREE_RANDOM_DISTRIBUTION_ENABLED=0",
        "PORTFOLIO_EXPOSURE_REQUIRE_DELIVERED=1",
        "REJECTION_DB_BATCH_SIZE=50",
    }
    assert all(item in source for item in required)


def test_legacy_telegram_package_cannot_shadow_dependency():
    assert not Path("telegram").exists()
    assert Path("legacy_telegram/__init__.py").exists()
    source = Path("legacy_telegram/__init__.py").read_text(encoding="utf-8")
    assert "prevents it from shadowing" in source


def test_ml_package_does_not_eagerly_import_training_stack():
    source = Path("ml/__init__.py").read_text(encoding="utf-8")
    assert "def __getattr__" in source
    assert "\nfrom ml import train_model\n" not in source
    assert 'import_module(f"{__name__}.{name}")' in source


def test_xgboost_thread_cap_is_not_hidden_in_error_branch():
    source = Path("engine/ml.py").read_text(encoding="utf-8")
    expected = '        booster_any: Any = booster\n        booster_any.set_param("nthread"'
    assert expected in source
    assert '            booster_any: Any = booster' not in source


def test_owner_beta_verifier_covers_release_boundaries():
    source = Path("scripts/verify_owner_beta_release.py").read_text(encoding="utf-8")
    required = {
        "scripts/schema_audit.py",
        "scripts/audit_db_session_calls.py",
        "scripts/architecture_smoke.py",
        "scripts/validate_governance_docs.py",
        "scripts/secret_scan.py",
        "scripts/production_readiness_check.py",
        "scripts/validate_env_contract.py",
        "tests/test_runtime_hotfix_20260725.py",
    }
    assert all(item in source for item in required)
    assert Path("docs/FINAL_OWNER_BETA_RELEASE_2026-07-25.md").exists()
