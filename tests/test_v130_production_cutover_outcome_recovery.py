from __future__ import annotations

import inspect
from pathlib import Path

from scripts.schema_audit import audit_outcome_projection_contract, audit_versions
from scripts.validate_env_contract import parse_env, validate

ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_and_single_migration_head() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.3"
    assert RELEASE_FINGERPRINT == "v1.3.3-full-system-certification-gates-20260801"
    audit = audit_versions(ROOT)
    assert audit["ok"] is True
    assert audit["heads"] == ["0031_perf_paper_reliability"]


def test_outcome_projection_guard_is_in_active_chain_and_orm() -> None:
    contract = audit_outcome_projection_contract(ROOT)
    assert contract == {
        "ok": True,
        "unique_guard_sql": True,
        "model_unique_constraint": True,
    }
    migration = (ROOT / "db/migrations/versions/0028_outcome_projection_guard.py").read_text(encoding="utf-8")
    assert "UPDATE outcome_notifications" in migration
    assert "DELETE FROM outcomes" in migration
    assert "existing_is_unique IS FALSE" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_outcomes_signal_id" in migration


def test_runtime_outcome_writer_no_longer_depends_on_on_conflict() -> None:
    import db.pg_features as pg_features

    source = inspect.getsource(pg_features.upsert_outcome)
    assert "on_conflict" not in source.lower()
    assert "pg_advisory_xact_lock" in source
    assert ".with_for_update()" in source
    assert "Outcome(" in source


def test_readiness_blocks_schema_drift_and_nonproduction_cutovers() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "uq_outcomes_signal_id" in source
    assert "duplicate_outcome_projections" in source
    assert '"production_cutover": _readiness_cutover_check(production=production)' in source
    assert "environment_not_production" in source
    assert "delivery_allowlist_not_empty" in source
    assert "missing_or_placeholder:TELEGRAM_BOT_TOKEN" not in source  # constructed dynamically
    assert "_is_unconfigured_runtime_value" in source
    assert "paystack_live_secret_invalid" in source
    assert "state_and_delivery_redis_not_distinct" in source


def test_staging_dependency_readiness_does_not_require_production_cutover(monkeypatch) -> None:
    import railway_main

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "signalrankai-staging")
    assert railway_main._production_readiness_required() is False

    check = railway_main._readiness_cutover_check(production=False)
    assert check["ok"] is True
    assert check["required"] is False
    assert check["production_detail"]


def test_production_dependency_readiness_keeps_cutover_fail_closed(monkeypatch) -> None:
    import railway_main

    monkeypatch.setenv("APP_ENV", "production")
    assert railway_main._production_readiness_required() is True
    assert railway_main._readiness_cutover_check(production=True)["required"] is True


def test_production_runtime_clears_staging_and_allowlist_state() -> None:
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "PUBLIC_TESTING_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACTIVE": "1",
        "DELIVERY_AUDIENCE_ALLOWLIST": "1409578077,2116406360",
        "RESEND_AUDIENCE_ALLOWLIST_ONLY": "1",
        "REAL_EXECUTION_ENABLED": "0",
    }
    result = apply_runtime_safety_environment(env)
    assert result.environment == "production"
    assert result.full_system_test_enabled is False
    assert env["PUBLIC_TESTING_MODE"] == "0"
    assert env["FULL_SYSTEM_STAGING_TEST_MODE"] == "0"
    assert env["FULL_SYSTEM_STAGING_TEST_ACTIVE"] == "0"
    assert env["DELIVERY_AUDIENCE_ALLOWLIST"] == ""
    assert env["RESEND_AUDIENCE_ALLOWLIST_ONLY"] == "0"
    assert result.audience_allowlist == ""


def test_production_profile_is_global_safe_and_provider_resilient() -> None:
    path = ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example"
    assert validate(path) == []
    values, keys = parse_env(path)
    assert len(keys) == len(set(keys))
    assert values["APP_ENV"] == "production"
    assert values["PUBLIC_TESTING_MODE"] == "0"
    assert values["FULL_SYSTEM_STAGING_TEST_MODE"] == "0"
    assert values["DELIVERY_AUDIENCE_ALLOWLIST"] == ""
    assert values["RESEND_AUDIENCE_ALLOWLIST_ONLY"] == "0"
    assert values["FREE_SIGNAL_DISTRIBUTION_ENABLED"] == "1"
    assert values["TRADINGVIEW_ENABLED"] == "0"
    assert values["RUN_ENGINE_LOOP"] == "1"
    assert values["RUN_WORKER_LOOP"] == "1"
    assert values["REAL_EXECUTION_ENABLED"] == "0"
    assert values["MT5_ALLOW_LIVE_ACCOUNTS"] == "0"
    assert values["PORTFOLIO_EXPOSURE_FAIL_OPEN"] == "0"
    assert values["STATE_REDIS_URL"] != values["DELIVERY_REDIS_URL"]


def test_yahoo_aliases_prevent_wti_equity_and_index_misrouting() -> None:
    from data.market_data import _get_yfinance_symbol_variants, format_ticker

    expected = {
        "WTI": "CL=F",
        "USOIL": "CL=F",
        "BRENT": "BZ=F",
        "GER40": "^GDAXI",
        "UK100": "^FTSE",
        "FRA40": "^FCHI",
        "US500": "^GSPC",
        "NAS100": "^NDX",
    }
    for symbol, ticker in expected.items():
        assert format_ticker(symbol, "yfinance") == ticker
    assert _get_yfinance_symbol_variants("EURUSD")[0] == "EURUSD=X"


def test_portfolio_classifies_commodities_before_exposure_counting() -> None:
    from engine.correlation_filter import PortfolioExposureManager

    manager = PortfolioExposureManager()
    assert manager._get_asset_class("WTI") == "commodity"
    assert manager._get_asset_class("XAUUSD") == "commodity"


def test_production_placeholder_detector_rejects_example_values() -> None:
    import ast

    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_is_unconfigured_runtime_value"
    )
    module = ast.Module(body=[helper_node], type_ignores=[])
    namespace: dict[str, object] = {}
    exec(compile(module, "railway_main.py", "exec"), namespace)
    helper = namespace["_is_unconfigured_runtime_value"]

    assert helper("") is True
    assert helper("<telegram-bot-token>") is True
    assert helper("changeme") is True
    assert helper("123456:real-shaped-token") is False


def test_railway_environment_name_overrides_spoofed_app_env(monkeypatch) -> None:
    import railway_main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    assert railway_main._runtime_environment_name() == "staging"
    assert railway_main._production_readiness_required() is False
