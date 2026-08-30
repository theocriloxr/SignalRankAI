from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_engine_circuit_breaker_uses_shared_async_bridge() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    assert "asyncio.get_event_loop().run_until_complete(circuit_breaker.check_market_health())" not in source
    assert "from utils.async_runner import run_sync as _run_async_check" in source
    assert "MARKET_CIRCUIT_BREAKER_TIMEOUT_SECONDS" in source


def test_websocket_ingestion_is_fail_safe_and_requires_master_flag(monkeypatch) -> None:
    monkeypatch.delenv("WS_INGEST_ENABLED", raising=False)
    monkeypatch.delenv("CRYPTO_WS_ENABLED", raising=False)
    import config as config_module

    module = importlib.reload(config_module)
    assert module.config.WS_INGEST_ENABLED is False
    assert module.config.CRYPTO_WS_ENABLED is False

    monkeypatch.setenv("WS_INGEST_ENABLED", "0")
    monkeypatch.setenv("CRYPTO_WS_ENABLED", "1")
    module = importlib.reload(config_module)
    assert module.config.CRYPTO_WS_ENABLED is False

    monkeypatch.setenv("WS_INGEST_ENABLED", "1")
    monkeypatch.setenv("CRYPTO_WS_ENABLED", "1")
    module = importlib.reload(config_module)
    assert module.config.CRYPTO_WS_ENABLED is True


def test_free_distribution_is_explicit_opt_in() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert 'FREE_SIGNAL_DISTRIBUTION_ENABLED"), True' not in source
    assert 'FREE_SIGNAL_DISTRIBUTION_ENABLED"), False' in source


def test_proxy_validation_never_uses_placeholder_provider() -> None:
    source = (ROOT / "worker" / "proxy_worker.py").read_text(encoding="utf-8")
    assert 'https://example.com/proxies' not in source
    assert 'PROXY_VALIDATION_ENABLED' in source
    assert 'proxy_validation_enabled' in source


def test_waitlist_jobs_are_decoupled_from_web_app() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    waitlist = (ROOT / "services" / "waitlist_jobs.py").read_text(encoding="utf-8")
    assert "from services.waitlist_jobs import" in source
    assert "async def check_waitlist_capacity_job" in waitlist
    assert "async def monitor_expired_invites_job" in waitlist


def test_webhook_503_has_structured_reason_and_readiness_secret_check() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "[webhook_rejected] reason=%s" in source
    assert 'checks["telegram_webhook_secret"]' in source
    assert 'reason="webhook_secret_not_configured"' in source
    assert "_webhook_queue_diagnostics" in source


def test_outcome_tracker_critical_session_is_labelled() -> None:
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert 'label="outcome_tracker.fetch_active_signals"' in source
    assert "get_pool_diagnostics" in source


def test_frontdoor_owns_migrations_and_predeploy_diagnostics() -> None:
    payload = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    assert "preDeployCommand" not in payload["deploy"]
    split = (ROOT / "split_signalrank_railway.ps1").read_text(encoding="utf-8")
    assert "scripts/controlled_migrate.py" in split
    assert "signalrank_migration_evidence.json" in split
    assert "deployment_diagnostics.py" in split
    assert "--strict-core" in split
    assert 'Set-ServiceConfig -Service $SourceService -Path "preDeployCommand"' in split


def test_deployment_diagnostics_and_protected_endpoint_present() -> None:
    assert (ROOT / "scripts" / "deployment_diagnostics.py").exists()
    diagnostics = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert "DEPLOYMENT_READINESS_RETRY_ATTEMPTS" in diagnostics
    assert "DEPLOYMENT_READINESS_RETRY_DELAY_SECONDS" in diagnostics
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert '@app.get("/diagnostics/deployment")' in source
    assert "DEPLOYMENT_DIAGNOSTICS_KEY" in source
    assert "DEPLOYMENT_FULL_TESTS_ENABLED" in source


def test_async_runner_ignores_test_only_disable_flag_on_railway() -> None:
    source = (ROOT / "utils" / "async_runner.py").read_text(encoding="utf-8")
    assert "if requested and railway:" in source
    assert "SIGNALRANK_DISABLE_BACKGROUND_THREADS ignored on Railway" in source


def test_market_circuit_breaker_has_regional_rest_fallbacks() -> None:
    source = (ROOT / "engine" / "market_circuit_breaker.py").read_text(encoding="utf-8")
    assert "coinbase,okx,binance" in source
    assert "api.exchange.coinbase.com" in source
    assert "www.okx.com" in source
    assert "all BTC reference providers unavailable" in source


def test_diagnostics_reports_missing_credentials_as_blocked_or_failed() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert 'BLOCKED = "BLOCKED"' in source
    assert "missing_permissions_or_credentials" in source
    assert "A PASS proves only the named check" in source
    assert "--run-full-suite" in source


def test_deployment_diagnostics_inspects_delivery_stream_backlog() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert "async def redis_delivery_queue_diagnostics" in source
    assert "xinfo_groups" in source
    assert "xpending_range" in source
    assert "oldest_pending_idle_ms" in source
    assert "dead_letter_depth" in source
    assert "legacy_list_depth" in source
    assert "async def redis_state_queue_diagnostics" in source


def test_predeploy_blocks_until_legacy_free_queue_is_reconciled() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert 'name="free_signal_queue_safety"' in source
    assert 'queue_status = BLOCKED if report.phase == "predeploy" else FAIL' in source
    assert "quarantine_free_signal_queue.py" in source


def test_free_queue_quarantine_is_non_destructive_and_dry_run_by_default() -> None:
    source = (ROOT / "scripts" / "quarantine_free_signal_queue.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--apply", action="store_true")' in source
    assert "delete(" not in source.lower()
    assert ".values(status=status)" in source
    assert 'label="ops.quarantine_free_signal_queue"' in source


def test_deployment_audit_inventory_covers_advanced_scanners() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    for scanner in ("ruff", "mypy", "pyright", "bandit", "pip-audit", "semgrep", "vulture", "shellcheck", "hadolint", "mutmut"):
        assert scanner in source
    assert "--extended-scans" in source
    assert (ROOT / "requirements-audit.txt").exists()


def test_active_signal_guard_migration_reconciles_legacy_duplicates() -> None:
    migration = (ROOT / "db" / "migrations" / "versions" / "0015_active_signal_guard.py").read_text(encoding="utf-8")
    assert "ROW_NUMBER() OVER" in migration
    assert "delivery_count DESC" in migration
    assert "has_open_outcome DESC" in migration
    assert "SET status = 'superseded'" in migration
    assert "rows_deleted', 0" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ix_signals_active_thesis" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "DELETE FROM signals" not in migration.upper()


def test_forward_active_guard_hardening_migration_and_ops_fallback_exist() -> None:
    migration = ROOT / "db" / "migrations" / "versions" / "0022_active_guard_reconcile.py"
    repair = ROOT / "scripts" / "repair_active_signal_duplicates.py"
    assert migration.exists()
    assert repair.exists()
    migration_source = migration.read_text(encoding="utf-8")
    repair_source = repair.read_text(encoding="utf-8")
    assert 'down_revision = "0021_runtime_truth_hardening"' in migration_source
    assert "has_delivery_proof DESC" in migration_source
    assert "--apply" in repair_source
    assert '"mode": "apply" if args.apply else "dry_run"' in repair_source
    assert '"rows_deleted": 0' in repair_source


def test_deployment_diagnostics_verifies_active_guard_database_truth() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert "active_duplicate_groups" in source
    assert "active_guard_unique_index" in source
    assert "ix_signals_active_thesis" in source
    assert "repair_active_signal_duplicates.py --apply" in source


def test_delivery_proof_columns_exist_before_later_proof_indexes() -> None:
    migration_0015 = (ROOT / "db" / "migrations" / "versions" / "0015_active_signal_guard.py").read_text(encoding="utf-8")
    migration_0017 = (ROOT / "db" / "migrations" / "versions" / "0017_signal_delivery_proof.py").read_text(encoding="utf-8")
    migration_0021 = (ROOT / "db" / "migrations" / "versions" / "0021_runtime_truth_hardening.py").read_text(encoding="utf-8")
    assert "ix_signal_deliveries_user_sent_ok_delivered_at" not in migration_0015
    assert "ADD COLUMN IF NOT EXISTS sent_ok" in migration_0017
    assert "ADD COLUMN IF NOT EXISTS attempt_count" in migration_0017
    assert "signal_deliveries(signal_id, sent_ok, delivery_state)" in migration_0021


def test_runtime_diagnostics_probe_the_launching_container() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "DEPLOYMENT_DIAGNOSTICS_BASE_URL" in source
    assert 'base_url = f"http://127.0.0.1:{port}"' in source


def test_railway_app_links_prefer_the_current_service_domain() -> None:
    command_source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    platform_source = (ROOT / "web" / "platform_api.py").read_text(encoding="utf-8")
    for source in (command_source, platform_source):
        railway = source.index('os.getenv("RAILWAY_PUBLIC_DOMAIN")')
        configured = source.index('os.getenv("APP_BASE_URL")', railway)
        assert railway < configured
        assert 'f"https://{base_url}"' in source or 'f"https://{configured}"' in source


def test_signal_insert_reuses_the_exact_active_unique_index_bucket() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    guard = source.index("[dedup] exact active bucket reused")
    insert = source.index("s = Signal(", guard)
    assert guard < insert
    for predicate in (
        "Signal.asset == asset",
        "Signal.direction == direction",
        "Signal.timeframe == timeframe",
        "Signal.expired.is_(False)",
        "Signal.archived.is_(False)",
    ):
        assert predicate in source[guard - 900 : insert]


def test_tradingview_metals_use_oanda_and_optional_failures_are_not_errors() -> None:
    source = (ROOT / "strategies" / "tradingview.py").read_text(encoding="utf-8")
    assert 'asset_upper in {"XAUUSD", "XAGUSD"}' in source
    assert "exchange = 'OANDA'" in source
    assert 'logger.error(f"[tradingview] rate_limit_exhausted' not in source
    assert 'logger.error(f"[tradingview] error fetching analysis' not in source
