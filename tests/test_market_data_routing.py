import time

import pytest


def _candles(timeframe_seconds=300, *, stale=False):
    end = time.time() - (timeframe_seconds * 10 if stale else 0)
    start = end - (29 * timeframe_seconds)
    return [
        {
            "timestamp": int((start + index * timeframe_seconds) * 1000),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1000.0,
        }
        for index in range(30)
    ]


def test_crypto_only_mode_filters_non_crypto(monkeypatch):
    from engine import core

    monkeypatch.setenv("CRYPTO_ONLY_MODE", "1")
    monkeypatch.delenv("ASSET_CLASSES_ENABLED", raising=False)
    assets = ["BTCUSDT", "EURUSD", "AAPL", "NAS100", "XAUUSD"]

    assert core._filter_assets_by_enabled_classes(assets) == ["BTCUSDT"]


def test_asset_classes_enabled_crypto_filters_non_crypto(monkeypatch):
    from engine import core

    monkeypatch.setenv("CRYPTO_ONLY_MODE", "0")
    monkeypatch.setenv("ASSET_CLASSES_ENABLED", "crypto")

    assert core._filter_assets_by_enabled_classes(["BTCUSDT", "EURUSD", "AAPL"]) == ["BTCUSDT"]


def test_stablecoin_trade_pairs_are_excluded():
    from data.pair_discovery import STABLECOIN_PAIRS, _filter_blacklisted

    stablecoins = ["USDCUSDT", "USDTUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "USDEUSDT"]
    assert set(stablecoins) <= STABLECOIN_PAIRS
    assert _filter_blacklisted(stablecoins + ["BTCUSDT"]) == ["BTCUSDT"]


def test_crypto_required_timeframes_ignore_optional_failures():
    from data.market_data import market_data_usability

    payload = {
        tf: {"candles": _candles(seconds), "source": "okx_connector"}
        for tf, seconds in (("5m", 300), ("15m", 900), ("1h", 3600))
    }
    result = market_data_usability(
        "BTCUSDT",
        ["1m", "5m", "15m", "1h", "4h", "1d"],
        payload,
    )

    assert result["usable"] is True
    assert all(result["required_timeframes"].values())
    assert result["optional_timeframes"] == {"1m": False, "4h": False, "1d": False}


def test_market_data_asset_count_uses_required_crypto_timeframes():
    from data.market_data import count_usable_market_data_assets

    payload = {
        tf: {"candles": _candles(seconds), "source": "okx_connector"}
        for tf, seconds in (("5m", 300), ("15m", 900), ("1h", 3600))
    }
    count = count_usable_market_data_assets(
        {"BTCUSDT": payload},
        {"BTCUSDT": ["1m", "5m", "15m", "1h", "4h", "1d"]},
    )

    assert count == 1


def test_cycle_queue_prunes_assets_removed_by_runtime_gate():
    from engine.cycle_queue import AssetCycleQueue

    queue = AssetCycleQueue()
    queue.refresh_universe(["BTCUSDT", "EURUSD", "AAPL"], force=True)
    queue.refresh_universe(["BTCUSDT"], force=True)

    assert queue.pop_batch(10) == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_fresh_exchange_data_beats_stale_crypto_cache(monkeypatch):
    from data import market_data

    monkeypatch.setenv("MARKET_CACHE_ENABLED", "1")
    monkeypatch.setenv("MARKET_CACHE_WRITE_THROUGH", "0")
    monkeypatch.setenv("MARKET_ALTERNATIVE_SIGNALS_ENABLED", "0")
    monkeypatch.setenv("TRADINGVIEW_ENABLED", "0")
    monkeypatch.setenv("YFINANCE_CRYPTO_PRIMARY_ENABLED", "0")

    async def fake_provider(asset, timeframe):
        seconds = {"5m": 300, "15m": 900, "1h": 3600}[timeframe]
        return _candles(seconds)

    async def fake_cached(session, symbol, timeframe, limit):
        return _candles({"5m": 300, "15m": 900, "1h": 3600}[timeframe], stale=True)

    class Session:
        async def commit(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(market_data, "async_get_candles", fake_provider)
    monkeypatch.setattr(market_data, "get_recent_candles", fake_cached)
    monkeypatch.setattr(market_data, "get_session", lambda: SessionContext())
    monkeypatch.setattr(market_data, "_get_last_provider_used", lambda asset, tf: "okx_connector")

    result = await market_data.fetch_market_data_cached("BTCUSDT", ["5m", "15m", "1h"])

    assert {result[tf]["source"] for tf in ("5m", "15m", "1h")} == {"okx_connector"}


@pytest.mark.asyncio
async def test_stale_successful_provider_payload_is_rejected(monkeypatch):
    from data import market_data

    monkeypatch.setenv("MARKET_CACHE_ENABLED", "0")
    monkeypatch.setenv("MARKET_CACHE_WRITE_THROUGH", "0")
    monkeypatch.setenv("MARKET_ALTERNATIVE_SIGNALS_ENABLED", "0")
    monkeypatch.setenv("TRADINGVIEW_ENABLED", "0")
    monkeypatch.setenv("YFINANCE_ENABLED", "0")
    monkeypatch.setenv("MARKET_PROVIDER_STALENESS_HARD_GATE_ENABLED", "1")

    async def stale_provider(asset, timeframe):
        return _candles(3600, stale=True)

    monkeypatch.setattr(market_data, "async_get_candles", stale_provider)
    monkeypatch.setattr(market_data, "_get_last_provider_used", lambda asset, tf: "stale_test_provider")

    result = await market_data.fetch_market_data_cached("XAUUSD", ["1h"])

    assert "1h" not in result
