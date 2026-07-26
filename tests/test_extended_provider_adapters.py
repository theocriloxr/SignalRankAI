from __future__ import annotations

import asyncio
from unittest.mock import patch


class DummyResponse:
    def __init__(self, payload=None, *, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def test_deribit_adapter_parses_parallel_arrays():
    from data.connectors.deribit_adapter import _async_get_candles

    response = DummyResponse(
        {
            "result": {
                "status": "ok",
                "ticks": [1700000000000, 1700000300000],
                "open": [100, 101],
                "high": [102, 103],
                "low": [99, 100],
                "close": [101, 102],
                "volume": [10, 11],
            }
        }
    )
    async def no_retry(fn, **_):
        return await fn()

    with patch("data.connectors.deribit_adapter.httpx_client.get_client", return_value=DummyClient(response)), patch(
        "data.connectors.deribit_adapter.httpx_client.retry_async", new=no_retry
    ):
        rows = asyncio.run(_async_get_candles("BTC-PERPETUAL", "5m", limit=2))
    assert len(rows) == 2
    assert rows[0]["close"] == 101.0


def test_eodhd_adapter_parses_daily_data(monkeypatch):
    from data.connectors.eodhd_adapter import _async_get_candles

    monkeypatch.setenv("EODHD_API_KEY", "test")
    response = DummyResponse(
        [
            {"date": "2026-01-02", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 20},
            {"date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        ]
    )
    with patch("data.connectors.eodhd_adapter.httpx_client.get_client", return_value=DummyClient(response)):
        rows = asyncio.run(_async_get_candles("AAPL", "1d", limit=2))
    assert [row["timestamp"] for row in rows] == ["2026-01-01", "2026-01-02"]


def test_marketstack_adapter_parses_nested_data(monkeypatch):
    from data.connectors.marketstack_adapter import _async_get_candles

    monkeypatch.setenv("MARKETSTACK_API_KEY", "test")
    response = DummyResponse(
        {
            "data": [
                {"date": "2026-01-01T10:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                {"date": "2026-01-01T11:00:00+00:00", "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 11},
            ]
        }
    )
    with patch("data.connectors.marketstack_adapter.httpx_client.get_client", return_value=DummyClient(response)):
        rows = asyncio.run(_async_get_candles("AAPL", "1h", limit=2))
    assert len(rows) == 2
    assert rows[-1]["close"] == 2.0


def test_finnhub_adapter_parses_candle_arrays(monkeypatch):
    from data.connectors.finnhub_adapter import _async_get_candles

    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    response = DummyResponse(
        {"s": "ok", "t": [1700000000, 1700003600], "o": [1, 2], "h": [2, 3], "l": [0.5, 1], "c": [1.5, 2.5], "v": [10, 11]}
    )
    with patch("data.connectors.finnhub_adapter.httpx_client.get_client", return_value=DummyClient(response)):
        rows = asyncio.run(_async_get_candles("AAPL", "1h", limit=2))
    assert rows[0]["timestamp"] == 1700000000000


def test_alpaca_adapter_requires_both_credentials_and_parses(monkeypatch):
    from data.connectors.alpaca_adapter import _async_get_candles

    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    response = DummyResponse(
        {"bars": [{"t": "2026-01-01T10:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}]}
    )
    client = DummyClient(response)
    with patch("data.connectors.alpaca_adapter.httpx_client.get_client", return_value=client):
        rows = asyncio.run(_async_get_candles("AAPL", "1h", limit=2))
    assert len(rows) == 1
    assert client.calls[0][1]["headers"]["APCA-API-KEY-ID"] == "key"


def test_tradier_adapter_parses_series(monkeypatch):
    from data.connectors.tradier_adapter import _async_get_candles

    monkeypatch.setenv("TRADIER_TOKEN", "token")
    response = DummyResponse(
        {"series": {"data": [{"time": "2026-01-01T10:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]}}
    )
    with patch("data.connectors.tradier_adapter.httpx_client.get_client", return_value=DummyClient(response)):
        rows = asyncio.run(_async_get_candles("AAPL", "5m", limit=2))
    assert len(rows) == 1


def test_stooq_adapter_parses_csv():
    from data.connectors.stooq_adapter import _async_get_candles

    text = "Date,Open,High,Low,Close,Volume\n2026-01-01,1,2,0.5,1.5,10\n2026-01-02,1.5,2.5,1,2,11\n"
    with patch("data.connectors.stooq_adapter.httpx_client.get_client", return_value=DummyClient(DummyResponse(text=text))):
        rows = asyncio.run(_async_get_candles("AAPL", "1d", limit=2))
    assert len(rows) == 2
    assert rows[-1]["close"] == 2.0


def test_nasdaq_data_link_adapter_uses_configured_dataset(monkeypatch):
    from data.connectors.nasdaq_data_link_adapter import _async_get_candles

    monkeypatch.setenv("NASDAQ_DATA_LINK_API_KEY", "key")
    monkeypatch.setenv("NASDAQ_DATA_LINK_DATASETS_JSON", '{"GC": "CHRIS/CME_GC1"}')
    response = DummyResponse(
        {
            "dataset_data": {
                "column_names": ["Date", "Open", "High", "Low", "Close", "Volume"],
                "data": [["2026-01-01", 1, 2, 0.5, 1.5, 10]],
            }
        }
    )
    with patch("data.connectors.nasdaq_data_link_adapter.httpx_client.get_client", return_value=DummyClient(response)):
        rows = asyncio.run(_async_get_candles("GC", "1d", limit=2))
    assert len(rows) == 1
    assert rows[0]["volume"] == 10.0


def test_connector_registry_exposes_derivative_and_keyed_stock_providers(monkeypatch):
    from data.connector_registry import get_providers_for_asset

    derivative_names = [name for name, _ in get_providers_for_asset("crypto_perpetual")]
    assert "deribit_connector" in derivative_names

    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    stock_names = [name for name, _ in get_providers_for_asset("stock")]
    assert "finnhub_connector" in stock_names
    assert "alpaca_connector" in stock_names
