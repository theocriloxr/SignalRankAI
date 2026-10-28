"""Production FX/index/commodity data failed as `insufficient_candles candles=0`.

Read-only engine logs (28 Oct 2026): Twelve Data failed in 0-2 ms (no network
call), Tiingo/Polygon/yfinance returned nothing, and the cause was only logged at
debug level. Connectors now report the cause, Polygon receives prefixed tickers
instead of raw platform symbols, and yfinance maps BRENT and the cash indices.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from data import provider_diagnostics as diag
from data.connectors import polygon_adapter, twelvedata_adapter, yfinance_adapter
from data.fetcher import _provider_failure_reason


@pytest.fixture(autouse=True)
def _clean():
    diag.reset()
    yield
    diag.reset()


def test_missing_key_is_reported_as_the_cause(monkeypatch):
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    assert asyncio.run(twelvedata_adapter._async_get_candles("GBPUSD", "15m")) == []
    assert diag.recent("twelvedata_connector") == "api_key_missing"
    reason = _provider_failure_reason("twelvedata_connector", "insufficient_candles", candles_count=0, latency_ms=1)
    assert reason == "twelvedata_connector:insufficient_candles cause=api_key_missing candles=0 latency_ms=1"


def test_active_cooldown_is_reported(monkeypatch):
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key-not-real")
    monkeypatch.setattr("data.providers._is_cooldown_active", lambda name: name == "twelvedata")
    assert asyncio.run(twelvedata_adapter._async_get_candles("GBPUSD", "15m")) == []
    assert diag.recent("twelvedata") == "rate_limit_cooldown_active"


def test_cause_is_only_attached_to_empty_results_and_expires(monkeypatch):
    diag.note("tiingo", "http_403")
    assert "cause=" not in _provider_failure_reason("tiingo_connector", "stale", candles_count=12)
    assert diag.recent("tiingo", max_age_seconds=0.0) is None


def test_each_provider_cause_is_warned_once_per_window(caplog):
    with caplog.at_level(logging.WARNING, logger="data.provider_diagnostics"):
        for _ in range(5):
            diag.note("polygon", "http_403")
        diag.note("polygon", "http_429")
    messages = [r.getMessage() for r in caplog.records]
    assert messages.count("[provider_unavailable] provider=polygon cause=http_403") == 1
    assert "[provider_unavailable] provider=polygon cause=http_429" in messages


@pytest.mark.parametrize("raw,expected", [
    ("NAS100", "I:NDX"), ("US500", "I:SPX"), ("US30", "I:DJI"), ("GER40", "I:DAX"), ("JP225", "I:NI225"),
    ("GBPUSD", "C:GBPUSD"), ("eur/usd", "C:EURUSD"), ("XAUUSD", "C:XAUUSD"),
    ("BTCUSDT", "X:BTCUSD"), ("ETHUSD", "X:ETHUSD"), ("AAPL", "AAPL"), ("I:VIX", "I:VIX"),
])
def test_polygon_receives_prefixed_tickers(raw, expected):
    assert polygon_adapter.polygon_ticker(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("BRENT", "BZ=F"), ("UKOIL", "BZ=F"), ("USOIL", "CL=F"), ("XAUUSD", "GC=F"),
    ("NAS100", "^NDX"), ("US500", "^GSPC"), ("US30", "^DJI"), ("GER40", "^GDAXI"), ("UK100", "^FTSE"),
    ("JP225", "^N225"), ("GBPUSD", "GBPUSD=X"), ("BTCUSDT", "BTC-USD"),
])
def test_yfinance_symbols_resolve_to_real_yahoo_tickers(raw, expected):
    assert yfinance_adapter._normalize_symbol(raw) == expected


def test_yfinance_builds_4h_from_utc_aligned_1h_bars(monkeypatch):
    pd = pytest.importorskip("pandas")
    requested = {}

    class Ticker:
        def __init__(self, symbol):
            requested["symbol"] = symbol

        def history(self, period, interval):
            requested["interval"] = interval
            index = pd.date_range("2026-10-27 00:00", periods=8, freq="1h", tz="UTC")
            return pd.DataFrame({"Open": range(1, 9), "High": range(2, 10), "Low": range(0, 8),
                                 "Close": range(1, 9), "Volume": [1.0] * 8}, index=index)

    monkeypatch.setattr(yfinance_adapter, "yf", type("YF", (), {"Ticker": Ticker}))
    bars = yfinance_adapter._sync_get_candles_impl("BRENT", "4h", limit=10)
    assert requested == {"symbol": "BZ=F", "interval": "1h"}
    assert [(b["open"], b["high"], b["low"], b["close"], b["volume"]) for b in bars] == [
        (1.0, 5.0, 0.0, 4.0, 4.0), (5.0, 9.0, 4.0, 8.0, 4.0)]
    assert bars[1]["timestamp"] - bars[0]["timestamp"] == 4 * 3600 * 1000
