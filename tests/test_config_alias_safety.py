from __future__ import annotations

import pytest

from core.env import runtime_environment_name, sanitized_config_fingerprint, validate_alias_conflicts


def test_conflicting_boolean_aliases_fail_closed(monkeypatch) -> None:
    """Alias groups that disagree on boolean value must raise."""
    monkeypatch.setenv("ENABLE_ML", "1")
    monkeypatch.setenv("ML_ENABLED", "0")
    with pytest.raises(RuntimeError, match="conflicting_boolean_environment_aliases"):
        validate_alias_conflicts()


def test_matching_boolean_aliases_are_allowed(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("AUTO_TRADE_ENABLED", "false")
    validate_alias_conflicts()


def test_conflicting_secret_aliases_are_not_raised(monkeypatch) -> None:
    """Secret aliases are intentionally not compared -- dual values can be a
    safe rotation state; provider authentication validates which is live.
    validate_alias_conflicts must NOT raise for differing secret aliases."""
    monkeypatch.setenv("META_API_TOKEN", "secret-one")
    monkeypatch.setenv("METAAPI_TOKEN", "secret-two")
    validate_alias_conflicts()  # Must not raise


def test_sanitized_fingerprint_does_not_embed_secret_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "very-secret-token")
    monkeypatch.setenv("REAL_EXECUTION_ENABLED", "0")
    fingerprint = sanitized_config_fingerprint(["TELEGRAM_BOT_TOKEN", "REAL_EXECUTION_ENABLED"])
    assert len(fingerprint) == 64
    assert "very-secret-token" not in fingerprint


def test_explicit_environment_override_requires_project_pin(monkeypatch) -> None:
    """SIGNALRANK_ENVIRONMENT_OVERRIDE only takes effect when the staging
    certification project ID matches the runtime Railway project ID.
    Without that pin, RAILWAY_ENVIRONMENT_NAME=production wins."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", "staging")
    # No STAGING_CERTIFICATION_PROJECT_ID / RAILWAY_PROJECT_ID set --
    # pinned_staging is False so the override is discarded.
    assert runtime_environment_name() == "production"


def test_explicit_environment_override_wins_when_pinned(monkeypatch) -> None:
    """When profile + project IDs all match, the staging override takes
    effect even on a Railway project named production."""
    project_id = "8d21a09b-8e45-4c10-87dd-e3568441153f"
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", "staging")
    monkeypatch.setenv("SIGNALRANK_ENV_PROFILE", "staging-certification")
    monkeypatch.setenv("STAGING_CERTIFICATION_PROJECT_ID", project_id)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", project_id)
    assert runtime_environment_name() == "staging"

