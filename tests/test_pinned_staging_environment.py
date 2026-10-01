from __future__ import annotations

from core.env import resolve_runtime_environment_name
from runtime_safety import apply_runtime_safety_environment
from scripts.quiescent_role import validate_quiescent_environment


STAGING_PROJECT = "8d21a09b-8e45-4c10-87dd-e3568441153f"


def _pinned_env() -> dict[str, str]:
    return {
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "RAILWAY_ENVIRONMENT": "production",
        "RAILWAY_PROJECT_ID": STAGING_PROJECT,
        "STAGING_CERTIFICATION_PROJECT_ID": STAGING_PROJECT,
        "SIGNALRANK_ENV_PROFILE": "staging-certification",
        "SIGNALRANK_ENVIRONMENT_OVERRIDE": "staging",
    }


def test_exact_pinned_staging_project_can_override_default_railway_label() -> None:
    env = _pinned_env()
    assert resolve_runtime_environment_name(env) == "staging"


def test_mismatched_project_id_cannot_spoof_staging() -> None:
    env = _pinned_env()
    env["RAILWAY_PROJECT_ID"] = "real-production-project"
    assert resolve_runtime_environment_name(env) == "production"


def test_missing_staging_pin_cannot_spoof_staging() -> None:
    env = _pinned_env()
    env.pop("STAGING_CERTIFICATION_PROJECT_ID")
    assert resolve_runtime_environment_name(env) == "production"


def test_wrong_profile_cannot_spoof_staging() -> None:
    env = _pinned_env()
    env["SIGNALRANK_ENV_PROFILE"] = "production-advisory"
    assert resolve_runtime_environment_name(env) == "production"


def test_runtime_safety_uses_pinned_staging_identity() -> None:
    env = _pinned_env()
    env["FULL_SYSTEM_STAGING_TEST_MODE"] = "0"
    result = apply_runtime_safety_environment(env)
    assert result.environment == "staging"
    assert env["REAL_EXECUTION_ENABLED"] == "0"
    assert env["AUTO_EXECUTION_ENABLED"] == "0"


def test_quiescent_role_accepts_exact_pinned_staging_project_only() -> None:
    env = _pinned_env()
    env.update(
        {
            "RUN_MODE": "analytics",
            "DECOMPOSED_TOPOLOGY_ENABLED": "1",
            "GLOBAL_EXECUTION_KILL_SWITCH": "1",
            "DATABASE_SCHEMA_GATE_ENABLED": "1",
            "RELEASE_SOURCE_GATE_ENABLED": "1",
            "REAL_EXECUTION_ENABLED": "0",
            "AUTO_EXECUTION_ENABLED": "0",
            "AUTO_TRADE_ENABLED": "0",
            "COPY_TRADE_ENABLED": "0",
            "MT5_ALLOW_LIVE_ACCOUNTS": "0",
            "BYBIT_EXECUTION_ENABLED": "0",
            "HYPERLIQUID_MAINNET_EXECUTION_ENABLED": "0",
            "REAL_PAYOUTS_ENABLED": "0",
            "AUTOMATIC_PAYOUTS_ENABLED": "0",
            "PAYSTACK_TRANSFERS_ENABLED": "0",
            "PAYMENTS_PUBLIC_ENABLED": "0",
        }
    )
    report = validate_quiescent_environment(env)
    assert report["status"] == "PASS"
    assert report["environment"] == "staging"

    env["RAILWAY_PROJECT_ID"] = "wrong-project"
    try:
        validate_quiescent_environment(env)
    except RuntimeError as exc:
        assert "requires staging environment" in str(exc)
    else:
        raise AssertionError("mismatched project ID must not pass staging certification")


def _install(monkeypatch, values: dict[str, str]) -> None:
    for key in (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "STAGING_CERTIFICATION_PROJECT_ID",
        "SIGNALRANK_ENV_PROFILE",
        "SIGNALRANK_ENVIRONMENT_OVERRIDE",
        "PRODUCTION_DB_BACKUP_VERIFIED",
        "PRODUCTION_DB_BACKUP_ID",
        "PRODUCTION_DB_BACKUP_CREATED_AT",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_controlled_migration_does_not_consume_production_backup_gate_in_pinned_staging(monkeypatch) -> None:
    from scripts import controlled_migrate

    env = _pinned_env()
    _install(monkeypatch, env)
    assert controlled_migrate._environment() == "staging"
    assert controlled_migrate._backup_errors() == []

    env["RAILWAY_PROJECT_ID"] = "real-production-project"
    _install(monkeypatch, env)
    assert controlled_migrate._environment() == "production"
    errors = controlled_migrate._backup_errors()
    assert "PRODUCTION_DB_BACKUP_VERIFIED must be 1" in errors


def test_staging_bootstrap_and_cleanup_share_pinned_identity(monkeypatch) -> None:
    from scripts import staging_migrate_and_bootstrap
    from tools import staging_cleanup

    env = _pinned_env()
    _install(monkeypatch, env)
    assert staging_migrate_and_bootstrap._environment() == "staging"
    assert staging_cleanup._environment() == "staging"
    assert staging_cleanup._is_production() is False

    env["RAILWAY_PROJECT_ID"] = "real-production-project"
    _install(monkeypatch, env)
    assert staging_migrate_and_bootstrap._environment() == "production"
    assert staging_cleanup._is_production() is True


def test_certification_and_analytics_share_pinned_identity(monkeypatch) -> None:
    from runtime import analytics
    from tools import staging_certification

    env = _pinned_env()
    _install(monkeypatch, env)
    assert staging_certification.environment_name() == "staging"
    assert analytics._production_runtime() is False

    env["RAILWAY_PROJECT_ID"] = "real-production-project"
    _install(monkeypatch, env)
    assert staging_certification.environment_name() == "production"
    assert analytics._production_runtime() is True
