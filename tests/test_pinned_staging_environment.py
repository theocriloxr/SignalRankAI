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
