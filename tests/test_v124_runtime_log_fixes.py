from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_railway_environment_is_authoritative_over_stale_app_env() -> None:
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "APP_ENV": "production",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "OWNER_TELEGRAM_ID": "1409578077",
        "PROXY_VALIDATION_ENABLED": "1",
    }
    result = apply_runtime_safety_environment(env)
    assert result.environment == "staging"
    assert result.acknowledgement_valid is True
    assert result.full_system_test_enabled is True
    assert env["FULL_SYSTEM_STAGING_TEST_ACTIVE"] == "1"
    assert env["PAPER_WORKER_DB_PRIORITY"] == "interactive"
    assert env["ADAPTIVE_CANDLE_DB_PRIORITY"] == "interactive"
    assert env["STAGING_QUALITY_GATES_ADVISORY"] == "1"
    assert env["PROXY_VALIDATION_ENABLED"] == "0"
    assert env["MT5_ALLOW_LIVE_ACCOUNTS"] == "0"
    assert env["BYBIT_TESTNET"] == "1"


def test_production_reports_ack_truthfully_but_never_activates_staging_mode() -> None:
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
    }
    result = apply_runtime_safety_environment(env)
    assert result.environment == "production"
    assert result.acknowledgement_valid is True
    assert result.full_system_test_enabled is False
    assert env["FULL_SYSTEM_STAGING_TEST_ACTIVE"] == "0"


def test_worker_priorities_use_validated_active_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FULL_SYSTEM_STAGING_TEST_ACTIVE", "1")
    monkeypatch.setenv("PAPER_WORKER_DB_PRIORITY", "background")
    monkeypatch.setenv("ADAPTIVE_CANDLE_DB_PRIORITY", "background")

    from core.paper_trading_service import _paper_worker_priority
    from engine.adaptive.candle_store import _capture_db_priority

    assert _paper_worker_priority() == "interactive"
    assert _capture_db_priority() == "interactive"


def test_log_driven_pipeline_repairs_are_present() -> None:
    source = (ROOT / "engine/core.py").read_text(encoding="utf-8")
    assert "STAGING_QUALITY_GATES_ADVISORY" in source
    assert "_append_staging_advisory" in source
    assert "'atr_pct': _filter_atr_pct" in source
    assert "'ema_20': _safe_float" in source
    assert "advanced_filters.run_all_filters(sig, market_filter_data, _filter_session)" in source
    assert "_maybe_log_heatmap(asset, cycle_no, len(final_signals))" in source


def test_readiness_checker_accepts_actual_health_routes() -> None:
    from scripts.production_readiness_check import run_readiness_checks

    result = run_readiness_checks(ROOT)
    assert result["ok"] is True
    checks = {row["name"]: row for row in result["checks"]}
    assert checks["web_health_routes"]["ok"] is True
