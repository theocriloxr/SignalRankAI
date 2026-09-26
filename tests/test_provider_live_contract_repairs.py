from __future__ import annotations

import asyncio
from types import SimpleNamespace

from data.provider_catalog import CertificationStatus, get_provider_spec
from scripts.certify_providers import certify_one


async def _retry_once(fn, *, retries=0, backoff=0.0):
    del retries, backoff
    return await fn()


class _Response:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_twelvedata_live_contract_sorts_oldest_first_and_honors_limit(monkeypatch):
    import data.connectors.twelvedata_adapter as td

    seen = {}

    class Client:
        async def get(self, url, *, params=None, timeout=None):
            seen["url"] = url
            seen["params"] = dict(params or {})
            seen["timeout"] = timeout
            return _Response(
                {
                    "values": [
                        {"datetime": "2026-09-26T12:00:00", "open": "3", "high": "4", "low": "2", "close": "3.5", "volume": "1"},
                        {"datetime": "2026-09-26T11:00:00", "open": "2", "high": "3", "low": "1", "close": "2.5", "volume": "1"},
                        {"datetime": "2026-09-26T10:00:00", "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "1"},
                    ]
                }
            )

    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setattr(td.httpx_client, "get_client", lambda name: Client())
    monkeypatch.setattr(td.httpx_client, "retry_async", _retry_once)

    rows = asyncio.run(td._async_get_candles("AAPL", "1h", limit=3))
    assert len(rows) == 3
    assert [row["open"] for row in rows] == [1.0, 2.0, 3.0]
    assert seen["params"]["outputsize"] == 3


def test_bybit_live_contract_uses_singular_v5_kline_endpoint(monkeypatch):
    import data.connectors.bybit_adapter as bybit

    seen = {}

    class Client:
        async def get(self, url, *, params=None, timeout=None):
            seen["url"] = url
            seen["params"] = dict(params or {})
            return _Response(
                {
                    "retCode": 0,
                    "result": {
                        "list": [
                            ["2000", "2", "3", "1", "2.5", "10"],
                            ["1000", "1", "2", "0.5", "1.5", "8"],
                        ]
                    },
                }
            )

    monkeypatch.setattr(bybit.httpx_client, "get_client", lambda name: Client())
    monkeypatch.setattr(bybit.httpx_client, "retry_async", _retry_once)
    rows = asyncio.run(bybit._async_get_candles("BTCUSDT", "5m", limit=2, timeout=2))

    assert seen["url"].endswith("/v5/market/kline")
    assert seen["params"]["category"] == "spot"
    assert [row["timestamp"] for row in rows] == [1000, 2000]


def test_tiingo_daily_equity_requests_history_window(monkeypatch):
    import data.connectors.tiingo_adapter as tiingo

    seen = {}

    class Client:
        async def get(self, url, *, params=None, timeout=None):
            seen["url"] = url
            seen["params"] = dict(params or {})
            return _Response(
                [
                    {"date": "2026-09-24T00:00:00.000Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
                    {"date": "2026-09-25T00:00:00.000Z", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 11},
                    {"date": "2026-09-26T00:00:00.000Z", "open": 3, "high": 4, "low": 2, "close": 3.5, "volume": 12},
                ]
            )

    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    monkeypatch.setattr(tiingo.httpx_client, "get_client", lambda name: Client())
    rows = asyncio.run(tiingo._async_get_candles("AAPL", "1d", limit=3, timeout=2))

    assert "/tiingo/daily/aapl/prices" in seen["url"]
    assert seen["params"]["startDate"]
    assert seen["params"]["token"] == "test-key"
    assert len(rows) == 3
    assert tiingo._split_pair("EURUSD") == ("EUR", "USD")
    assert tiingo._split_pair("BTCUSDT") == ("BTC", "USDT")


def test_coingecko_resolves_quote_suffixed_symbol(monkeypatch):
    import data.connectors.coingecko_adapter as cg

    monkeypatch.setattr(cg, "_COOLDOWN_UNTIL", {})
    cg._symbol_to_id_cache().clear()

    async def fake_get(url, *, name, params=None, headers=None, timeout=8.0, retries=2):
        del url, name, params, headers, timeout, retries
        return [
            {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
            {"id": "ethereum", "symbol": "eth", "name": "Ethereum"},
        ]

    monkeypatch.setattr(cg, "async_http_get_json", fake_get)
    assert asyncio.run(cg._async_resolve_id("BTCUSDT")) == "bitcoin"
    assert cg._base_symbol("ETH-USD") == "ETH"


def test_coinmetrics_uses_exchange_qualified_market_and_iso_time(monkeypatch):
    import data.connectors.coinmetrics_adapter as cm

    seen = []

    async def fake_get(url, *, name, params=None, headers=None, timeout=8.0, retries=2):
        del url, name, headers, timeout, retries
        seen.append(dict(params or {}))
        return {
            "data": [
                {
                    "time": "2026-09-26T12:00:00Z",
                    "price_open": "100",
                    "price_high": "102",
                    "price_low": "99",
                    "price_close": "101",
                    "volume": "5",
                },
                {
                    "time": "2026-09-26T13:00:00Z",
                    "price_open": "101",
                    "price_high": "103",
                    "price_low": "100",
                    "price_close": "102",
                    "volume": "6",
                },
            ]
        }

    monkeypatch.setattr(cm, "async_http_get_json", fake_get)
    monkeypatch.setattr(cm, "_EMPTY_CACHE", {})
    rows = asyncio.run(cm._async_get_candles("BTCUSDT", "1h", limit=2, timeout=2))

    assert seen[0]["markets"] == "binance-btc-usdt-spot"
    assert seen[0]["frequency"] == "1h"
    assert rows[0]["timestamp"] < rows[1]["timestamp"]
    assert rows[-1]["close"] == 102.0


def test_fmp_external_block_classification_is_non_secret():
    import data.connectors.fmp_adapter as fmp

    status, reason = fmp._classify_external_block(
        403, "This endpoint is available on a premium subscription."
    )
    assert status == "BLOCKED_PAID_PLAN"
    assert "premium" in reason.lower()

    status, _ = fmp._classify_external_block(429, "Too many requests")
    assert status == "BLOCKED_RATE_LIMIT"


def test_alphavantage_external_block_classification_is_non_secret():
    from data.providers import _classify_alphavantage_block

    status, _ = _classify_alphavantage_block(
        200, "Thank you for using Alpha Vantage. Please subscribe to a premium plan."
    )
    assert status == "BLOCKED_PAID_PLAN"

    status, _ = _classify_alphavantage_block(429, "rate limit reached")
    assert status == "BLOCKED_RATE_LIMIT"


def test_provider_certifier_honors_adapter_blocker_hint(monkeypatch):
    import data.connectors.fmp_adapter as fmp

    monkeypatch.setenv("FMP_ENABLED", "1")
    monkeypatch.setenv("FMP_API_KEY", "configured-key")
    monkeypatch.setattr(fmp, "get_candles", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        fmp,
        "certification_hint",
        lambda: {
            "status": CertificationStatus.BLOCKED_PAID_PLAN.value,
            "reason": "intraday endpoint requires the configured plan entitlement",
        },
    )

    result = asyncio.run(
        certify_one(get_provider_spec("fmp"), live=True, timeout=1, limit=2)
    )
    assert result.certification_status == CertificationStatus.BLOCKED_PAID_PLAN.value
    assert "plan entitlement" in (result.error or "")


def test_coinmetrics_falls_back_to_pair_candles_when_markets_are_empty(monkeypatch):
    import data.connectors.coinmetrics_adapter as cm

    calls = []

    async def fake_get(url, *, name, params=None, headers=None, timeout=8.0, retries=2):
        del name, headers, timeout, retries
        calls.append((url, dict(params or {})))
        if url.endswith("/timeseries/market-candles"):
            return {"data": []}
        assert url.endswith("/timeseries/pair-candles")
        return {
            "data": [
                {
                    "pair": "btc-usd",
                    "time": "2026-09-25T00:00:00.000000000Z",
                    "price_open": "100",
                    "price_high": "102",
                    "price_low": "99",
                    "price_close": "101",
                },
                {
                    "pair": "btc-usd",
                    "time": "2026-09-26T00:00:00.000000000Z",
                    "price_open": "101",
                    "price_high": "103",
                    "price_low": "100",
                    "price_close": "102",
                },
            ]
        }

    monkeypatch.setattr(cm, "async_http_get_json", fake_get)
    monkeypatch.setattr(cm, "_EMPTY_CACHE", {})
    rows = asyncio.run(cm._async_get_candles("BTCUSDT", "1d", limit=2, timeout=2))

    assert any(url.endswith("/timeseries/pair-candles") for url, _ in calls)
    pair_call = next(params for url, params in calls if url.endswith("/timeseries/pair-candles"))
    assert pair_call["pairs"] == "btc-usd"
    assert pair_call["paging_from"] == "end"
    assert len(rows) == 2
    assert rows[0]["timestamp"] < rows[1]["timestamp"]
    assert rows[-1]["close"] == 102.0
