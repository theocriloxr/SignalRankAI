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


def test_railway_runs_migrations_and_predeploy_diagnostics() -> None:
    payload = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    command = payload["deploy"]["preDeployCommand"]
    assert "alembic upgrade head" in command
    assert "deployment_diagnostics.py" in command
    assert "--strict-core" in command


def test_deployment_diagnostics_and_protected_endpoint_present() -> None:
    assert (ROOT / "scripts" / "deployment_diagnostics.py").exists()
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


def test_predeploy_does_not_hide_or_block_only_on_legacy_free_queue() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert 'name="free_signal_queue_safety"' in source
    assert 'queue_status = WARN if report.phase == "predeploy" else FAIL' in source
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
