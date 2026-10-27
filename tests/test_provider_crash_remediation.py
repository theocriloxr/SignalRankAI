from __future__ import annotations

import asyncio
import time
import pytest

from data import fetcher, connector_registry


@pytest.fixture(autouse=True)
def isolated_provider_cooldowns(monkeypatch):
    from data import providers
    monkeypatch.setattr(providers, "_PROVIDER_COOLDOWN", {})


def _rows(now=None):
    latest = (time.time() if now is None else now) - 30
    return [{"timestamp": latest - (24 - i) * 300, "open": 100, "high": 101,
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
    started = 1_800_000_000.0
    clock = [started]
    cache = {("EURUSD", "5m"): (started - 10, _rows(started))}
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", cache)
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher.time, "time", lambda: clock[0])
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", "1")
    monkeypatch.setenv("CANDLE_REQUEST_CACHE_TTL_SECONDS", "1")
    monkeypatch.setenv("CANDLE_FORWARD_FILL_TTL_SECONDS", "30")
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    monkeypatch.setattr(fetcher, "_fetch_fx_multi_provider", lambda *args: [])
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    assert cache[("EURUSD", "5m")][0] == started - 10
    clock[0] = started + 19
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    clock[0] = started + 21
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


@pytest.mark.parametrize("symbol,expected", [
    ("EURUSD", "EUR/USD"), ("EUR/USD", "EUR/USD"), ("XAUUSD", "XAU/USD"),
    ("BTCUSDT", "BTC/USDT"), ("AAPL", "AAPL"), ("BRK-B", "BRK-B"),
    ("NAS100", "NAS100"),
])
def test_twelvedata_preserves_provider_symbol_semantics(symbol, expected):
    from data.symbol_formatter import format_symbol_for_twelvedata
    from data.dynamic_symbol_assign import format_symbol_for_twelvedata as dynamic
    assert format_symbol_for_twelvedata(symbol) == expected
    assert dynamic(symbol)[0] == expected


def test_twelvedata_requests_utc_and_honors_offset_timestamps(monkeypatch):
    from data.connectors import twelvedata_adapter as td
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "local-alias-test")
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {"values": [
                {"datetime": stamp, "open": 1, "high": 2, "low": 0.5, "close": 1}
                for stamp in ["2026-10-02T12:00:00", "2026-10-02T13:00:00+01:00"]
            ]}
    class Client:
        async def get(self, url, **kwargs):
            calls.append(kwargs)
            return Response()
    monkeypatch.setattr(td.httpx_client, "get_client", lambda _: Client())
    rows = asyncio.run(td._async_get_candles("EURUSD", "5m"))
    assert calls[0]["params"]["symbol"] == "EUR/USD"
    assert calls[0]["params"]["timezone"] == "UTC"
    assert [row["timestamp"] for row in rows] == [1790942400000, 1790942400000]
    assert asyncio.run(td._async_get_candles("EURUSD", "3m")) == []
    assert len(calls) == 1


@pytest.mark.parametrize("http_status", [200, 429])
def test_twelvedata_quota_stops_adapter_and_legacy_requests(monkeypatch, http_status, caplog):
    from data import providers
    from data.connectors import twelvedata_adapter as td
    monkeypatch.setenv("TWELVEDATA_API_KEY", "secret-must-not-be-logged")
    calls = []
    class Response:
        status_code = http_status
        def json(self):
            return {"status": "error", "message": "You have run out of API credits for the day. secret-must-not-be-logged"}
    class Client:
        async def get(self, *args, **kwargs):
            calls.append(1)
            return Response()
    monkeypatch.setattr(td.httpx_client, "get_client", lambda _: Client())
    monkeypatch.setattr(providers.requests, "get", lambda *args, **kwargs: pytest.fail("quota cooldown ignored by legacy provider"))
    assert asyncio.run(td._async_get_candles("EURUSD", "5m")) == []
    assert asyncio.run(td._async_get_candles("XAUUSD", "5m")) == []
    assert providers.fetch_twelvedata_candles("AAPL", "5m") == []
    assert calls == [1]
    assert "secret-must-not-be-logged" not in caplog.text
