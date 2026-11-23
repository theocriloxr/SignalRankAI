"""*_PREFERRED_PROVIDER goes first within an explicit allowlist (23 Nov 2026).

Production set FX/STOCK/INDEX/COMMODITY_PREFERRED_PROVIDER=yfinance and an explicit
*_MARKET_DATA_PROVIDERS list; the preference was ignored under the list, so forex and stock
fetches spent their two attempts on rate-limited free tiers and non-crypto data went stale.
"""
from __future__ import annotations

import asyncio
import time

from data import fetcher


def _fresh(n=60, step=300):
    now = int(time.time()) // step * step
    return [{"timestamp": (now - (n - i) * step) * 1000, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1,
             "volume": 1.0} for i in range(n)]


def _run(monkeypatch, preferred: str | None, within: str = "1"):
    calls: list[str] = []

    def make(name):
        async def fn(symbol, tf, timeout=10):
            calls.append(name)
            return _fresh()
        return fn

    providers = [(n, make(n)) for n in ("twelvedata_connector", "tiingo_connector", "yfinance_connector")]
    import data.connector_registry as reg

    monkeypatch.setattr(reg, "get_async_providers_for_asset", lambda kind: list(providers))
    monkeypatch.setenv("FX_MARKET_DATA_PROVIDERS", "twelvedata,tiingo,yfinance")
    monkeypatch.setenv("OHLC_PREFERRED_WITHIN_ALLOWLIST", within)
    if preferred:
        monkeypatch.setenv("FX_PREFERRED_PROVIDER", preferred)
    else:
        monkeypatch.delenv("FX_PREFERRED_PROVIDER", raising=False)
    monkeypatch.setattr(fetcher, "_provider_cooling_down", lambda name: False)
    asyncio.run(fetcher.async_get_candles("EURUSD", "5m"))
    return calls


def test_preferred_provider_is_tried_first_within_the_allowlist(monkeypatch):
    assert _run(monkeypatch, "yfinance")[:1] == ["yfinance_connector"]


def test_without_a_preference_the_allowlist_order_stands(monkeypatch):
    assert _run(monkeypatch, None)[:1] == ["twelvedata_connector"]


def test_switch_restores_the_old_strict_order(monkeypatch):
    assert _run(monkeypatch, "yfinance", within="0")[:1] == ["twelvedata_connector"]
