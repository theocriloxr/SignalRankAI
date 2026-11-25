"""Yahoo downloads are cached per (symbol, interval, period); 4h reuses the 1h download (25 Nov 2026)."""
from __future__ import annotations

import pandas as pd

from data.connectors import yfinance_adapter as ya


class _Ticker:
    calls: list = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period, interval):
        _Ticker.calls.append((self.symbol, interval, period))
        idx = pd.date_range("2026-11-20", periods=80, freq="1h", tz="UTC")
        return pd.DataFrame({"Open": 1.0, "High": 1.1, "Low": 0.9, "Close": 1.0, "Volume": 1.0}, index=idx)


def test_one_download_serves_repeat_scans_and_4h(monkeypatch):
    _Ticker.calls = []
    monkeypatch.setattr(ya, "yf", type("YF", (), {"Ticker": _Ticker}))
    monkeypatch.setattr(ya, "_HISTORY_CACHE", {})
    a = ya._sync_get_candles_impl("UK100", "1h")
    b = ya._sync_get_candles_impl("UK100", "1h")
    c = ya._sync_get_candles_impl("UK100", "4h")
    assert a and a == b and c
    assert _Ticker.calls == [("^FTSE", "1h", "60d")]


def test_cache_expires_inside_the_freshness_limit(monkeypatch):
    _Ticker.calls = []
    monkeypatch.setattr(ya, "yf", type("YF", (), {"Ticker": _Ticker}))
    monkeypatch.setattr(ya, "_HISTORY_CACHE", {})
    monkeypatch.setenv("YFINANCE_HISTORY_CACHE_SCALE", "0")
    ya._sync_get_candles_impl("EURUSD", "5m")
    ya._sync_get_candles_impl("EURUSD", "5m")
    assert len(_Ticker.calls) == 2
    for tf, ttl in ya._TTL_SECONDS.items():
        bar = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}[tf]
        assert ttl < bar  # always well inside the 2x-bar freshness limit
