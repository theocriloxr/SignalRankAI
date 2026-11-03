"""A provider with no symbol for an asset never uses up a fetch attempt (3 Nov 2026).

Production: all ten indices had no candles on every timeframe. The index order
(INDEX_MARKET_DATA_PROVIDERS=fmp,twelvedata,polygon,alphavantage,yfinance) left
twelvedata, polygon, yfinance after FMP/Alpha Vantage dropped out (no index
candle connector), and the budget of two attempts per timeframe went to
twelvedata (rate-limited) and polygon — mapped to None for seven indices — so
yfinance was never tried.
"""
from __future__ import annotations

import pytest

from data import fetcher

PROVIDERS = [("twelvedata_connector", object()), ("polygon_connector", object()), ("yfinance_connector", object())]


@pytest.fixture
def strict_index_order(monkeypatch):
    monkeypatch.setenv("INDEX_MARKET_DATA_PROVIDERS", "fmp,twelvedata,polygon,alphavantage,yfinance")
    monkeypatch.delenv("OHLC_INDEX_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", raising=False)
    monkeypatch.delenv("OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", raising=False)


@pytest.mark.parametrize("asset", ["GER40", "UK100", "JP225", "FRA40", "EU50", "AUS200", "HK50"])
def test_indices_polygon_cannot_serve_reach_yfinance(strict_index_order, asset):
    ordered = fetcher._ordered_provider_candidates(PROVIDERS, asset_kind="index", timeframe="1h", asset=asset)
    assert [name for name, _ in ordered] == ["twelvedata_connector", "yfinance_connector"]


def test_a_provider_with_a_mapping_keeps_its_place(strict_index_order):
    ordered = fetcher._ordered_provider_candidates(PROVIDERS, asset_kind="index", timeframe="1h", asset="US500")
    assert [name for name, _ in ordered] == ["twelvedata_connector", "polygon_connector"]


def test_symbol_support_reads_the_asset_map():
    assert not fetcher._provider_supports_symbol("polygon_connector", "AUS200")
    assert fetcher._provider_supports_symbol("yfinance_connector", "AUS200")
    assert fetcher._provider_supports_symbol("polygon_legacy", "US500")
    assert fetcher._provider_supports_symbol("binance_connector", "UNMAPPEDXYZ")  # no map entry: not excluded
    assert fetcher._provider_supports_symbol("polygon_connector", "")
