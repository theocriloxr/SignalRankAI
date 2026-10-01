from __future__ import annotations

import pytest

from core.env import sanitized_config_fingerprint, validate_alias_conflicts


def test_conflicting_boolean_aliases_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "0")
    with pytest.raises(RuntimeError, match="conflicting_boolean_environment_aliases"):
        validate_alias_conflicts()


def test_matching_boolean_aliases_are_allowed(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "false")
    validate_alias_conflicts()


def test_conflicting_secret_aliases_fail_without_leaking_values(monkeypatch) -> None:
    monkeypatch.setenv("META_API_TOKEN", "secret-one")
    monkeypatch.setenv("METAAPI_TOKEN", "secret-two")
    with pytest.raises(RuntimeError) as exc:
        validate_alias_conflicts()
    message = str(exc.value)
    assert "META_API_TOKEN" in message and "METAAPI_TOKEN" in message
    assert "secret-one" not in message and "secret-two" not in message


def test_sanitized_fingerprint_does_not_embed_secret_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "very-secret-token")
    monkeypatch.setenv("REAL_EXECUTION_ENABLED", "0")
    fingerprint = sanitized_config_fingerprint(["TELEGRAM_BOT_TOKEN", "REAL_EXECUTION_ENABLED"])
    assert len(fingerprint) == 64
    assert "very-secret-token" not in fingerprint
