from __future__ import annotations

import asyncio
import pytest

from data import fetcher, connector_registry


def _rows():
    return [{"timestamp": 1_700_000_000 + i * 300, "open": 100, "high": 101,
             "low": 99, "close": 100, "volume": 1} for i in range(25)]


@pytest.mark.parametrize("enabled", ["1", "true", "yes", "on", " TRUE "])
def test_sync_configured_provider_is_used_for_boolean_aliases(monkeypatch, enabled):
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", enabled)
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", {})
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    calls = []
    def provider(*args):
        calls.append("configured")
        return _rows()
    def legacy(*args):
        pytest.fail("configured provider routing fell through to legacy premium FX")
    monkeypatch.setattr(fetcher, "_fetch_fx_multi_provider", provider)
    monkeypatch.setattr(fetcher, "get_fx_candles", legacy)
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    assert calls == ["configured"]


@pytest.mark.parametrize("enabled", ["1", "true", "yes", "on", " TRUE "])
def test_async_configured_provider_preserves_lineage(monkeypatch, enabled):
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", enabled)
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    monkeypatch.setattr(fetcher, "_LAST_PROVIDER_USED", {})
    async def provider(*args, **kwargs):
        return _rows()
    monkeypatch.setattr(connector_registry, "get_async_providers_for_asset",
                        lambda _: [("twelvedata_connector", provider)])
    def legacy(*args):
        pytest.fail("async configured routing used legacy synchronous fetcher")
    monkeypatch.setattr(fetcher, "get_candles", legacy)
    rows = asyncio.run(fetcher.async_get_candles("EURUSD", "5m"))
    assert len(rows) == 25
    assert fetcher._get_last_provider_used("EURUSD", "5m") == "twelvedata_connector"


def test_repeated_provider_failure_does_not_extend_forward_fill_lifetime(monkeypatch):
    clock = [100.0]
    cache = {("EURUSD", "5m"): (90.0, _rows())}
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", cache)
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher.time, "time", lambda: clock[0])
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", "1")
    monkeypatch.setenv("CANDLE_REQUEST_CACHE_TTL_SECONDS", "1")
    monkeypatch.setenv("CANDLE_FORWARD_FILL_TTL_SECONDS", "30")
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    monkeypatch.setattr(fetcher, "_fetch_fx_multi_provider", lambda *args: [])
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    assert cache[("EURUSD", "5m")][0] == 90.0
    clock[0] = 119.0
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    clock[0] = 121.0
    assert fetcher.get_candles("EURUSD", "5m") == []


@pytest.mark.parametrize("kind", ["fx", "stock", "index", "commodity"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_disabled_yahoo_is_absent_from_adapters_and_legacy_fallbacks(monkeypatch, kind, asynchronous):
    monkeypatch.setenv("YFINANCE_ENABLED", "0")
    get_providers = connector_registry.get_async_providers_for_asset if asynchronous else connector_registry.get_providers_for_asset
    names = [name for name, _ in get_providers(kind)]
    assert "yfinance_connector" not in names
    assert "yahoo_legacy" not in names


def test_polygon_requests_recent_bars_and_returns_bounded_chronological_candles(monkeypatch):
    from data.connectors import polygon_adapter
    monkeypatch.setenv("POLYGON_API_KEY", "local-test-key")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.setenv("MASSIVE_MARKET_DATA_ENABLED", "1")
    requests = []
    class Response:
        status_code = 200
        def json(self):
            return {"results": [{"t": timestamp, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1} for timestamp in [500000, 100000, 400000]]}
    class Client:
        async def get(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()
    monkeypatch.setattr(polygon_adapter.httpx_client, "get_client", lambda _: Client())
    rows = asyncio.run(polygon_adapter._async_get_candles("AAPL", "5m", limit=2))
    assert [row["timestamp"] for row in rows] == [400000, 500000]
    assert requests[0][1]["params"]["sort"] == "desc"
    assert requests[0][1]["params"]["limit"] == 10
    assert "/range/5/minute/" in requests[0][0]
    requests.clear()
    assert asyncio.run(polygon_adapter._async_get_candles("AAPL", "unsupported", limit=2)) == []
    assert requests == []
