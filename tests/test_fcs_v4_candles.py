from __future__ import annotations

import asyncio

import pytest

from data.connectors import fcs_adapter as fcs


@pytest.fixture
def client(monkeypatch):
    from data import providers
    monkeypatch.setattr(providers, "_PROVIDER_COOLDOWN", {})
    monkeypatch.setenv("FCS_API_KEY", "private-test-key-must-not-appear")
    monkeypatch.delenv("FCS_SYMBOL_MAP_JSON", raising=False)
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {"status": True, "code": 200, "response": {
                str(stamp): {"t": stamp, "o": 100, "h": 101, "l": 99, "c": 100, "v": None}
                for stamp in [1_800_000_000, 1_799_999_400, 1_799_999_700]}}
    class Client:
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()
    monkeypatch.setattr(fcs.httpx_client, "get_client", lambda _: Client())
    return calls, Response


@pytest.mark.parametrize("symbol,market,ticker", [("EUR/USD", "forex", "EURUSD"),
    ("XAUUSD", "forex", "XAUUSD"), ("AAPL", "stock", "AAPL"),
    ("BRK-B", "stock", "BRK-B"), ("NAS100", "stock", "NAS100"),
    ("BTCUSDT", "crypto", "BTCUSDT"), ("NASDAQ:AAPL", "stock", "NASDAQ:AAPL")])
def test_documented_history_endpoint_preserves_instrument_and_parses_source(client, symbol, market, ticker):
    calls, _ = client
    bars = asyncio.run(fcs._async_get_candles(symbol, "5m", limit=2, timeout=3))
    assert [bar["timestamp"] for bar in bars] == [1_799_999_700, 1_800_000_000]
    url, args = calls[0]
    assert url == f"https://api-v4.fcsapi.com/{market}/history"
    assert "private-test-key" not in url
    assert args["timeout"] == 3
    assert args["json"]["symbol"] == ticker
    assert args["json"]["period"] == "5m"
    assert args["json"]["length"] == 2


@pytest.mark.parametrize("symbol,timeframe", [("AAPL", "3m"), ("unknown-market-123!", "5m")])
def test_unsupported_request_does_not_default_to_another_timeframe_or_instrument(client, symbol, timeframe):
    calls, _ = client
    assert asyncio.run(fcs._async_get_candles(symbol, timeframe)) == []
    assert calls == []


def test_symbol_mapping_requires_valid_configuration(client, monkeypatch):
    calls, _ = client
    monkeypatch.setenv("FCS_SYMBOL_MAP_JSON", "invalid")
    assert asyncio.run(fcs._async_get_candles("NAS100", "5m")) == []
    assert calls == []
    monkeypatch.setenv("FCS_SYMBOL_MAP_JSON", '{"NAS100":"NASDAQ:NDX"}')
    assert asyncio.run(fcs._async_get_candles("NAS100", "5m"))
    assert calls[0][1]["json"]["symbol"] == "NASDAQ:NDX"


def test_network_failures_and_provider_messages_never_expose_credentials(client, caplog, monkeypatch):
    calls, response = client
    monkeypatch.setattr(response, "json", lambda _: {"status": False, "code": 401,
        "msg": "private-test-key-must-not-appear", "response": {}})
    assert asyncio.run(fcs._async_get_candles("EURUSD", "5m")) == []
    assert "private-test-key-must-not-appear" not in caplog.text


def test_quota_failure_applies_cooldown(client, monkeypatch):
    calls, response = client
    monkeypatch.setattr(response, "status_code", 429)
    assert asyncio.run(fcs._async_get_candles("EURUSD", "5m")) == []
    assert asyncio.run(fcs._async_get_candles("XAUUSD", "5m")) == []
    assert len(calls) == 1


def test_corrupt_candles_fail_closed(client, monkeypatch):
    _, response = client
    monkeypatch.setattr(response, "json", lambda _: {"response": {"x": {"t": 1_800_000_000,
        "o": 100, "h": 1, "l": 99, "c": 100}}})
    assert asyncio.run(fcs._async_get_candles("EURUSD", "5m")) == []
