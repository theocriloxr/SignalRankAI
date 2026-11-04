"""Every pinned index reaches Yahoo under its Yahoo symbol (4 Nov 2026).

Production: FRA40, EU50, AUS200 and HK50 were requested from yfinance as their own
names; Yahoo returned nothing (`yfinance_connector:insufficient_candles
cause=empty_response:HK50`), so those indices had no candles on any timeframe.
"""
from __future__ import annotations

import pytest

from data.connectors.yfinance_adapter import _normalize_symbol
from services import asset_mapper


INDICES = ["US500", "NAS100", "US30", "GER40", "UK100", "JP225", "FRA40", "EU50", "AUS200", "HK50"]


@pytest.mark.parametrize("asset", INDICES)
def test_index_uses_a_yahoo_symbol(asset):
    assert _normalize_symbol(asset).startswith("^")


@pytest.mark.parametrize("asset", ["FRA40", "EU50", "AUS200", "HK50"])
def test_adapter_matches_the_asset_mapper(asset):
    assert _normalize_symbol(asset) == asset_mapper._INDEX_MAP[asset]["yfinance"]


def test_forex_and_crypto_unchanged():
    assert _normalize_symbol("EURUSD") == "EURUSD=X"
    assert _normalize_symbol("BTCUSDT") == "BTC-USD"
    assert _normalize_symbol("BRENT") == "BZ=F"
