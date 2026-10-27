"""Instrument identity, feed authority and isolated SDK failure boundaries."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data import sdk_gateway
from market_data_sdk import worker as sdk_worker
from data.connectors import sdk_adapters
from data.provider_catalog import get_provider_spec


def bar(stamp=1_800_000_000):
    return dict(timestamp=stamp, open=10, high=12, low=9, close=11, volume=5)


@pytest.mark.parametrize("symbol,expected", [("BTCUSDT", "BTC/USDT"), ("BTCUSDC", "BTC/USDC"),
    ("BTC-USD", "BTC/USD"), ("ETH/BTC", "ETH/BTC"), ("BTC", None), ("BTC/USDT:USDT", None)])
def test_spot_identity_preserves_currency(symbol, expected):
    assert sdk_adapters.crypto_pair(symbol) == expected


def test_sdk_bars_are_sorted_deduplicated_and_checked():
    assert sdk_worker.normalize_bars([bar(1_800_000_300_000), bar(), bar()], 2) == [
        bar(1_800_000_000_000), bar(1_800_000_300_000)]
    with pytest.raises(ValueError, match="conflicting"):
        sdk_worker.normalize_bars([bar(), {**bar(), "close": 10}], 2)


@pytest.mark.parametrize("bad", [{"timestamp": "2026-01-01T00:00:00"}, {"high": 8},
    {"volume": -1}, {"close": float("nan")}, {"timestamp": float("inf")}])
def test_malformed_sdk_bars_fail_closed(bad):
    with pytest.raises(ValueError):
        sdk_worker.normalize_bars([{**bar(), **bad}], 1)


def test_gateway_receives_only_operation_credentials_and_no_orders(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "must-not-pass")
    monkeypatch.setenv("DATABASE_URL", "must-not-pass")
    monkeypatch.setenv("BYBIT_API_SECRET", "must-not-pass")
    monkeypatch.setenv("MARKETDATA_TOKEN", "marketdata-only")
    monkeypatch.setenv("ALPACA_API_KEY", "alpaca-only")
    monkeypatch.delenv("MARKET_DATA_SDK_PYTHON", raising=False)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert Path(kwargs["cwd"]).is_dir()
        assert not list(Path(kwargs["cwd"]).iterdir())
        return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "data": [bar()]}))

    monkeypatch.setattr(subprocess, "run", run)
    assert sdk_gateway.read_sdk("marketdata_bars", {"symbol": "AAPL"}, timeout=90) == [bar()]
    args, kwargs = calls[0]
    assert args[1] == "-I" and kwargs["timeout"] == 30
    env = kwargs["env"]
    assert env["MARKETDATA_TOKEN"] == "marketdata-only"
    assert not {"TELEGRAM_TOKEN", "DATABASE_URL", "BYBIT_API_SECRET", "ALPACA_API_KEY"} & set(env)
    assert not Path(kwargs["cwd"]).exists()
    with pytest.raises(ValueError, match="unsupported"):
        sdk_gateway.read_sdk("place_order", {})


@pytest.mark.parametrize("response", ["not-json", '{"ok":false,"error":"missing"}',
                                     '{"ok":true,"data":null}'])
def test_bad_worker_response_is_unavailable(monkeypatch, response):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=response))
    assert sdk_gateway.read_sdk("ccxt_bars", {}) is None


def test_worker_timeout_does_not_expose_child_secrets(monkeypatch, caplog):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("secret-url", 1, stderr="secret-token")
    monkeypatch.setattr(subprocess, "run", run)
    assert sdk_gateway.read_sdk("ccxt_bars", {}, timeout=1) is None
    assert "secret" not in caplog.text


def test_ccxt_explicit_venue_and_exact_spot_market(monkeypatch):
    monkeypatch.setenv("CCXT_MARKET_DATA_EXCHANGE", "kraken")
    with patch.object(sdk_adapters, "read_sdk", return_value=[bar()]) as read:
        assert sdk_adapters.ccxt_get_candles("BTCUSDT", "5m")
        assert read.call_args.args[1]["symbol"] == "BTC/USDT"
        assert read.call_args.args[1]["venue"] == "kraken"
        assert sdk_adapters.ccxt_get_candles("BTCUSDT:USDT", "5m") == []
        monkeypatch.setenv("CCXT_MARKET_DATA_EXCHANGE", "arbitrary-server")
        assert sdk_adapters.ccxt_get_candles("BTCUSDT", "5m") == []
        assert read.call_count == 1


def test_ibkr_requires_exact_instrument_type_and_currency(monkeypatch):
    monkeypatch.setenv("IBKR_MARKET_DATA_HOST", "127.0.0.1")
    monkeypatch.setenv("IBKR_MARKET_DATA_PORT", "4002")
    monkeypatch.setenv("IBKR_MARKET_DATA_CONTRACTS_JSON", json.dumps({
        "EURUSD": dict(symbol="EUR", currency="USD", exchange="IDEALPRO", secType="CASH"),
        "NAS100": dict(conId=123, currency="USD", exchange="CME", secType="FUT"),
        "GBPUSD": dict(symbol="EUR", currency="USD", exchange="IDEALPRO", secType="CASH")}))
    with patch.object(sdk_adapters, "read_sdk", return_value=[bar()]) as read:
        assert sdk_adapters.ibkr_get_candles("EURUSD", "5m")
        assert sdk_adapters.ibkr_get_candles("GBPUSD", "5m") == []
        assert sdk_adapters.ibkr_get_candles("NAS100", "5m") == []
        assert sdk_adapters.ibkr_get_candles("AAPL", "5m") == []
        assert read.call_count == 1


@pytest.mark.parametrize("provider,key,value", [("alpaca", "ALPACA_DATA_FEED", "delayed_sip"),
    ("marketdata", "MARKETDATA_MODE", "delayed"), ("marketdata", "MARKETDATA_MODE", "cached")])
def test_delayed_mode_cannot_certify_fresh_bars(monkeypatch, provider, key, value):
    from scripts.certify_providers import _freshness_validation
    from data.fetcher import _provider_timeframe_eligible
    monkeypatch.setenv(key, value)
    spec = get_provider_spec(provider)
    assert not spec.execution_data_allowed()
    assert not _freshness_validation(spec, {"last_timestamp": datetime.now(timezone.utc).timestamp()})[0]
    assert not _provider_timeframe_eligible(provider + "_connector", "1h")


def test_sdk_registry_is_opt_in_and_respects_explicit_order(monkeypatch):
    from data.connector_registry import get_providers_for_asset
    for key in ("CCXT_MARKET_DATA_ENABLED", "MARKETDATA_ENABLED", "IBKR_MARKET_DATA_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    assert not {"ccxt_connector", "marketdata_connector", "ibkr_connector"} & {
        name for kind in ("crypto", "stock", "fx") for name, _ in get_providers_for_asset(kind)}
    monkeypatch.setenv("CCXT_MARKET_DATA_ENABLED", "1")
    monkeypatch.setenv("CCXT_MARKET_DATA_EXCHANGE", "kraken")
    monkeypatch.setenv("CRYPTO_MARKET_DATA_PROVIDERS", "ccxt,okx")
    assert [name for name, _ in get_providers_for_asset("crypto")] == ["ccxt_connector", "okx_connector"]


def test_alpaca_exact_pair_feed_and_latest_order(monkeypatch):
    from data.connectors import alpaca_adapter as alpaca
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_API_SECRET", "test")
    monkeypatch.setenv("ALPACA_DATA_TRANSPORT", "rest")
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    calls = []

    async def get(url, **kw):
        calls.append((url, kw))
        symbol = kw["params"].get("symbols")
        row = dict(t="2026-01-01T00:00:00Z", o=10, h=12, l=9, c=11, v=2)
        return SimpleNamespace(status_code=200, json=lambda: {"bars": {symbol: [row]} if symbol else [row]})

    monkeypatch.setattr(alpaca.httpx_client, "get_client", lambda *_: SimpleNamespace(get=get))
    assert asyncio.run(alpaca._async_get_candles("BTCUSDT", "5m"))
    assert calls[-1][1]["params"]["symbols"] == "BTC/USDT"
    assert asyncio.run(alpaca._async_get_candles("AAPL", "5m"))
    assert calls[-1][1]["params"]["feed"] == "iex"
    assert calls[-1][1]["params"]["sort"] == "desc"
    assert asyncio.run(alpaca._async_get_candles("EUR/USD", "5m")) == []


def test_alpaca_wrong_instrument_payload_is_rejected(monkeypatch):
    from data.connectors import alpaca_adapter as alpaca
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_API_SECRET", "test")
    async def get(*a, **kw):
        return SimpleNamespace(status_code=200, json=lambda: {"bars": {"ETH/USD": [bar()]}})
    monkeypatch.setattr(alpaca.httpx_client, "get_client", lambda *_: SimpleNamespace(get=get))
    assert asyncio.run(alpaca._async_get_candles("BTCUSD", "5m")) == []


def test_coinbase_does_not_label_six_hour_bars_as_four_hours():
    from data.connectors.coinbase_adapter import _normalize_product, _granularity_seconds
    assert _normalize_product("BTCUSDT") == "BTC-USDT"
    assert _normalize_product("BTCUSDC") == "BTC-USDC"
    assert _granularity_seconds("4h") == 0
    assert "4h" not in get_provider_spec("coinbase").timeframes


@pytest.mark.asyncio
async def test_coinbase_stream_uses_typed_quote_and_exact_instrument(monkeypatch):
    import data.get_live_price as prices
    from data.provider_types import LivePriceQuote
    monkeypatch.setenv("COINBASE_QUOTE_TRANSPORT", "websocket")
    prices._price_breakers.clear()
    monkeypatch.setattr(sdk_adapters, "coinbase_stream_quote", lambda *a, **kw: dict(
        symbol="BTC-USDT", last=100, bid=99, ask=101, timestamp=datetime.now(timezone.utc).timestamp()))
    quote = await prices._fetch_coinbase_quote("BTCUSDT")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider_symbol == "BTC-USDT"
    assert quote.bid == 99 and quote.ask == 101
    assert "websocket_source" in quote.confidence_reasons
