from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import production_health
from scripts.production_health import HealthCheck
from scripts.validate_env_contract import parse_env, validate


ROOT = Path(__file__).resolve().parents[1]
PROFILE_NAMES = (
    "railway-hobby-full-advisory.env.example",
    "railway-hobby-owner-beta.env.example",
    "railway-hobby-paper-demo.env.example",
    "railway-hobby-real-execution-gated.env.example",
)


def test_required_railway_hobby_profiles_are_safe_and_complete() -> None:
    required = {
        "PUBLIC_TESTING_MODE": "0",
        "AUTO_MIGRATE": "0",
        "DB_POOL_SIZE_RAILWAY": "2",
        "DB_MAX_OVERFLOW_RAILWAY": "0",
        "DB_POOL_TIMEOUT_SECONDS": "15",
        "DB_MAX_CONCURRENT_SESSIONS": "2",
        "REDIS_MAX_CONNECTIONS": "24",
        "UVICORN_WORKERS": "1",
        "WEBHOOK_UPDATE_WORKERS": "4",
        "WEBHOOK_UPDATE_QUEUE_SIZE": "1000",
        "RESOURCE_GUARD_ENABLED": "1",
        "APP_MEMORY_LIMIT_MB": "0",
        "APP_MEMORY_SOFT_RATIO": "0.72",
        "APP_MEMORY_HARD_RATIO": "0.88",
        "APP_MEMORY_RECOVERY_MARGIN_MB": "32",
        "AUTO_TRADE_ENABLED": "0",
        "COPY_TRADE_ENABLED": "0",
        "REAL_EXECUTION_ENABLED": "0",
        "MT5_ALLOW_LIVE_ACCOUNTS": "0",
    }
    for name in PROFILE_NAMES:
        path = ROOT / "configs" / "env" / name
        assert path.exists()
        assert validate(path) == []
        values, keys = parse_env(path)
        assert len(keys) == len(set(keys))
        assert all(values.get(key) == expected for key, expected in required.items())
        assert values["STATE_REDIS_URL"] != values["DELIVERY_REDIS_URL"]


def test_env_validator_rejects_invalid_resource_thresholds() -> None:
    profile = ROOT / "tests" / "fixtures" / "invalid-resource.env.example"
    assert any("memory ratios" in error for error in validate(profile))


def test_safe_error_never_echoes_exception_text() -> None:
    marker = "redis://user:SUPER_SECRET@example.invalid"
    result = production_health._safe_error(RuntimeError(marker))
    assert result == "error=RuntimeError"
    assert marker not in result


@pytest.mark.asyncio
async def test_http_health_contract_checks_all_three_endpoints(monkeypatch) -> None:
    def fake_get(url: str, timeout_seconds: float):
        del timeout_seconds
        if url.endswith("/livez"):
            return 200, {"status": "live"}
        if url.endswith("/healthz"):
            return 200, {"status": "healthy"}
        if url.endswith("/readyz"):
            return 200, {"status": "ready"}
        raise AssertionError(url)

    monkeypatch.setattr(production_health, "_http_get_json", fake_get)
    result = await production_health.collect_health(
        base_url="https://service.example",
        include_dependencies=False,
    )
    assert result["ok"] is True
    assert result["summary"] == {"passed": 3, "failed": 0, "total": 3}


@pytest.mark.asyncio
async def test_readyz_degraded_is_a_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        production_health,
        "_http_get_json",
        lambda _url, _timeout: (200, {"status": "degraded"}),
    )
    check = await production_health.check_http_endpoint(
        "https://service.example",
        "/readyz",
        timeout_seconds=1,
    )
    assert check.ok is False
    assert check.detail == "status_code=200;status_contract=invalid"


@pytest.mark.asyncio
async def test_dependency_report_checks_distinct_state_and_delivery_redis(
    monkeypatch,
) -> None:
    async def fake_postgres(**_kwargs):
        return HealthCheck("postgres", True, 1, "query=ok")

    async def fake_redis(name: str, _url: str, **_kwargs):
        return HealthCheck(name, True, 1, "ping=ok")

    monkeypatch.setattr(production_health, "check_postgres", fake_postgres)
    monkeypatch.setattr(production_health, "check_redis_url", fake_redis)
    secret_env = {
        "DATABASE_URL": "postgresql://user:DO_NOT_PRINT@db/private",
        "STATE_REDIS_URL": "redis://:STATE_SECRET@state/private",
        "DELIVERY_REDIS_URL": "redis://:DELIVERY_SECRET@delivery/private",
        "REQUIRE_DISTINCT_DELIVERY_REDIS": "1",
    }
    result = await production_health.collect_health(
        base_url="",
        include_http=False,
        environ=secret_env,
    )
    rendered = json.dumps(result)
    assert result["ok"] is True
    assert result["summary"] == {"passed": 4, "failed": 0, "total": 4}
    assert "DO_NOT_PRINT" not in rendered
    assert "STATE_SECRET" not in rendered
    assert "DELIVERY_SECRET" not in rendered


def test_redis_topology_fails_when_delivery_redis_is_shared() -> None:
    check = production_health.check_redis_topology(
        {
            "STATE_REDIS_URL": "redis://same",
            "DELIVERY_REDIS_URL": "redis://same",
            "REQUIRE_DISTINCT_DELIVERY_REDIS": "1",
        }
    )
    assert check.ok is False
    assert check.detail == "delivery_redis_not_distinct"
