from __future__ import annotations

import pytest

from core.env import SafetyFlags, env_bool_alias


def test_boolean_alias_conflict_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("ML_ENABLED", "1")
    monkeypatch.setenv("ENABLE_ML", "0")
    with pytest.raises(RuntimeError, match="conflicting_boolean_aliases"):
        env_bool_alias("ML_ENABLED", "ENABLE_ML", default=True)


def test_boolean_alias_same_value_is_accepted(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("INDICES_ENABLED", "1")
    monkeypatch.setenv("INDEX_ENABLED", "true")
    assert env_bool_alias("INDICES_ENABLED", "INDEX_ENABLED", default=False) is True


def test_unsafe_execution_dependency_configuration_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("REAL_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("AUTO_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "1")
    monkeypatch.setenv("COPY_TRADE_ENABLED", "0")
    monkeypatch.setenv("MT5_ALLOW_LIVE_ACCOUNTS", "0")
    monkeypatch.setenv("BYBIT_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("REAL_PAYOUTS_ENABLED", "0")
    monkeypatch.setenv("PAYMENTS_ENABLED", "0")
    with pytest.raises(RuntimeError, match="unsafe_safety_flag_configuration"):
        SafetyFlags.from_env()


def test_safe_execution_defaults_remain_fail_closed(monkeypatch) -> None:
    for name in (
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "MT5_ALLOW_LIVE_ACCOUNTS",
        "BYBIT_EXECUTION_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "PAYMENTS_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    flags = SafetyFlags.from_env()
    assert not flags.enabled_names()
