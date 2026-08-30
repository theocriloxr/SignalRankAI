from __future__ import annotations

import logging

import pytest

import railway_main
from scripts.post_deploy_smoke import _derive_base_url
from utils.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_SERVICE_NAME",
        "APP_ENV",
        "ENVIRONMENT",
        "APP_BASE_URL",
        "WEBHOOK_DOMAIN",
        "WEBHOOK_URL",
        "DATABASE_URL",
        "STATE_REDIS_URL",
        "SIGNALRANK_STATE_REDIS_URL",
        "REDIS_URL",
        "DELIVERY_REDIS_URL",
        "TELEGRAM_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_current_railway_domain_overrides_copied_production_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "signalrankai-staging.up.railway.app")
    monkeypatch.setenv("APP_BASE_URL", "https://signalrankai-production.up.railway.app")

    assert railway_main._get_webhook_url() == "https://signalrankai-staging.up.railway.app"
    assert _derive_base_url(None) == "https://signalrankai-staging.up.railway.app"


def test_production_webhook_contract_requires_durable_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")

    errors = railway_main._production_webhook_contract_errors()
    assert "DATABASE_URL" in errors
    assert "STATE_REDIS_URL|REDIS_URL" in errors
    assert "DELIVERY_REDIS_URL" in errors
    assert "TELEGRAM_WEBHOOK_SECRET" in errors


def test_production_webhook_contract_accepts_distinct_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@postgres.internal/db")
    monkeypatch.setenv("STATE_REDIS_URL", "redis://state.internal:6379")
    monkeypatch.setenv("DELIVERY_REDIS_URL", "redis://delivery.internal:6379")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "strong-secret")

    assert railway_main._production_webhook_contract_errors() == []


def test_production_webhook_contract_rejects_shared_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@postgres.internal/db")
    monkeypatch.setenv("STATE_REDIS_URL", "redis://shared.internal:6379")
    monkeypatch.setenv("DELIVERY_REDIS_URL", "redis://shared.internal:6379")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "strong-secret")

    assert "DISTINCT_REDIS_SERVICES" in railway_main._production_webhook_contract_errors()


def test_logging_suppresses_token_bearing_http_client_urls() -> None:
    setup_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
