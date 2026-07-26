from __future__ import annotations

import asyncio

from services.provider_registry import ProviderRegistry


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def hmget(self, key, names):
        return [self.values.get((key, name)) for name in names]

    async def hset(self, key, name, value):
        self.values[(key, name)] = value


def test_registry_has_no_import_time_network_and_fails_closed(monkeypatch):
    monkeypatch.setenv("BINANCE_MARKET_DATA_ENABLED", "0")
    registry = ProviderRegistry(redis_client=FakeRedis())
    asyncio.run(registry.initialize(["coinbase", "okx"]))

    # Deliberately make every compatible provider unavailable.
    for provider in registry._providers.values():
        provider.is_active = False
    assert asyncio.run(registry.get_provider("BTCUSD", "crypto_spot")) is None


def test_registry_persists_cooldown_and_recovers_on_success():
    redis = FakeRedis()
    alerts = []

    async def alert(provider, category):
        alerts.append((provider, category))

    registry = ProviderRegistry(redis_client=redis, alert_callback=alert, cooldown_seconds=1)
    asyncio.run(registry.initialize(["coinbase"]))
    asyncio.run(registry.report_failure("coinbase", "HTTP 429", 429))
    health = registry.get_health("coinbase")
    assert health["is_healthy"] is False
    assert health["cooldown_until"] is not None
    assert alerts == [("coinbase", "rate_limit")]

    asyncio.run(registry.report_success("coinbase"))
    health = registry.get_health("coinbase")
    assert health["is_healthy"] is True
    assert health["cooldown_until"] is None


def test_registry_uses_asset_capability_not_generic_order(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    registry = ProviderRegistry(redis_client=FakeRedis())
    asyncio.run(registry.initialize())
    # yfinance is the only configured stock source in the catalogue here.
    assert asyncio.run(registry.get_provider("AAPL", "equity")) == "yfinance"
