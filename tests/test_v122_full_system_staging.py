from __future__ import annotations

import inspect
from pathlib import Path


def test_full_system_staging_mode_enables_feature_paths_and_keeps_sandbox_boundaries():
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "APP_ENV": "staging",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "OWNER_TELEGRAM_ID": "1409578077",
    }
    result = apply_runtime_safety_environment(env)
    assert result.full_system_test_enabled is True
    for name in (
        "REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED", "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED", "BYBIT_EXECUTION_ENABLED", "PAYMENTS_ENABLED",
        "PAYMENTS_PUBLIC_ENABLED",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED", "FREE_RANDOM_DISTRIBUTION_ENABLED",
        "WS_INGEST_ENABLED", "WS_CRYPTO_ENABLED", "CRYPTO_WS_ENABLED",
        "PAPER_TRADING_ENABLED", "PAPER_AUTO_EXECUTION_ENABLED",
    ):
        assert env[name] == "1"
    assert env["REAL_PAYOUTS_ENABLED"] == "0"
    assert env["PAYMENTS_PUBLIC_TEST_MODE"] == "1"
    assert env["MT5_ALLOW_LIVE_ACCOUNTS"] == "0"
    assert env["BYBIT_TESTNET"] == "1"
    assert env["PAYMENTS_PUBLIC_TEST_MODE"] == "1"
    assert env["DELIVERY_AUDIENCE_ALLOWLIST"] == "1409578077"


def test_missing_acknowledgement_fails_closed():
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "APP_ENV": "staging",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "wrong",
        "REAL_EXECUTION_ENABLED": "1",
        "PAYMENTS_PUBLIC_ENABLED": "1",
    }
    result = apply_runtime_safety_environment(env)
    assert result.full_system_test_enabled is False
    assert env["REAL_EXECUTION_ENABLED"] == "0"
    assert env["PAYMENTS_PUBLIC_ENABLED"] == "0"


def test_regular_staging_preserves_all_explicit_free_distribution():
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "APP_ENV": "staging",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED": "1",
        "FREE_RANDOM_DISTRIBUTION_ENABLED": "1",
        "REAL_EXECUTION_ENABLED": "1",
    }
    result = apply_runtime_safety_environment(env)

    assert result.full_system_test_enabled is False
    assert env["FREE_SIGNAL_DISTRIBUTION_ENABLED"] == "1"
    assert "FREE_SIGNAL_DISTRIBUTION_ENABLED" not in result.forced_off
    assert env["FREE_RANDOM_DISTRIBUTION_ENABLED"] == "1"
    assert "FREE_RANDOM_DISTRIBUTION_ENABLED" not in result.forced_off
    assert env["REAL_EXECUTION_ENABLED"] == "0"


def test_production_preserves_all_explicit_free_distribution():
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "APP_ENV": "production",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED": "1",
        "FREE_RANDOM_DISTRIBUTION_ENABLED": "1",
    }
    result = apply_runtime_safety_environment(env)

    assert result.environment == "production"
    assert env["FREE_SIGNAL_DISTRIBUTION_ENABLED"] == "1"
    assert "FREE_SIGNAL_DISTRIBUTION_ENABLED" not in result.forced_off
    assert env["FREE_RANDOM_DISTRIBUTION_ENABLED"] == "1"
    assert "FREE_RANDOM_DISTRIBUTION_ENABLED" not in result.forced_off


def test_incomplete_production_financial_activation_fails_closed():
    from runtime_safety import apply_runtime_safety_environment

    env = {"APP_ENV": "production", "REAL_EXECUTION_ENABLED": "1"}
    result = apply_runtime_safety_environment(env)
    assert result.environment == "production"
    assert env["REAL_EXECUTION_ENABLED"] == "0"
    assert "REAL_EXECUTION_ENABLED" in result.forced_off


def test_live_mt5_account_requires_separate_permission(monkeypatch):
    from execution.service import ExecutionGate, ExecutionRequest

    monkeypatch.setenv("REAL_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("MT5_ALLOW_LIVE_ACCOUNTS", "0")
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "1")
    request = ExecutionRequest(
        user_id=1, signal_id="sig-1", account_id="acct-1", tier="enterprise", mode="auto",
        signal={"entry": 100.0, "stop_loss": 99.0, "direction": "buy"},
        user_enabled=True, consent=True, account_ready=True, account_is_demo=False,
        credentials_encrypted=True, quote_trusted=True, quote_age_seconds=1.0,
        max_quote_age_seconds=15.0, market_open=True, risk_allowed=True,
        evidence_allowed=True, broker_healthy=True, resources_available=True,
        reconciliation_ready=True, kill_switch=False,
    )
    decision = ExecutionGate().preflight(request)
    assert decision.allowed is False
    assert "MT5_LIVE_ACCOUNTS_DISABLED" in decision.reasons


def test_v122_profile_contains_all_workflow_flags():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "SignalRankAI_v1.2.2_Railway_Full_System_Staging_Test.env.example").read_text(encoding="utf-8")
    for line in (
        "FULL_SYSTEM_STAGING_TEST_MODE=1",
        "REAL_EXECUTION_ENABLED=1",
        "AUTO_TRADE_ENABLED=1",
        "COPY_TRADE_ENABLED=1",
        "BYBIT_EXECUTION_ENABLED=1",
        "BYBIT_TESTNET=1",
        "PAYMENTS_ENABLED=1",
        "PAYMENTS_PUBLIC_ENABLED=1",
        "PAYMENTS_PUBLIC_TEST_MODE=1",
        "REAL_PAYOUTS_ENABLED=1",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED=1",
        "FREE_RANDOM_DISTRIBUTION_ENABLED=1",
        "WS_INGEST_ENABLED=1",
        "PAPER_AUTO_EXECUTION_ENABLED=1",
        "MT5_ALLOW_LIVE_ACCOUNTS=0",
    ):
        assert line in profile


def test_canonical_staging_profile_enables_all_free_distribution():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "RAILWAY_ENV_UPDATED.env.example").read_text(encoding="utf-8")

    for line in (
        "FREE_SIGNAL_DISTRIBUTION_ENABLED=1",
        "FREE_RANDOM_DISTRIBUTION_ENABLED=1",
        "RESEND_INCLUDE_FREE=1",
        "RESEND_AUDIENCE_ALLOWLIST_ONLY=0",
        "DELIVERY_AUDIENCE_RESTRICTION_MODE=0",
        "DELIVERY_AUDIENCE_ALLOWLIST=",
    ):
        assert line in profile


def test_current_production_profiles_enable_all_free_distribution():
    root = Path(__file__).resolve().parents[1]

    for filename in (
        "SignalRankAI_v1.3.3_Railway_Production_Advisory.env.example",
        "SignalRankAI_v1.3.3_Railway_Live_Owner_Canary.env.example",
    ):
        profile = (root / filename).read_text(encoding="utf-8")
        assert "FREE_SIGNAL_DISTRIBUTION_ENABLED=1" in profile
        assert "FREE_RANDOM_DISTRIBUTION_ENABLED=1" in profile


def test_live_paystack_key_disables_money_paths_in_staging():
    from runtime_safety import apply_runtime_safety_environment

    env = {
        "APP_ENV": "staging",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "OWNER_TELEGRAM_ID": "1409578077",
        "PAYSTACK_SECRET_KEY": "sk_live_forbidden",
    }
    result = apply_runtime_safety_environment(env)
    assert result.full_system_test_enabled is True
    assert env["PAYMENTS_ENABLED"] == "0"
    assert env["PAYMENTS_PUBLIC_ENABLED"] == "0"
    assert env["REAL_PAYOUTS_ENABLED"] == "0"
    assert "PAYSTACK_LIVE_KEY_REJECTED" in result.hard_boundaries
