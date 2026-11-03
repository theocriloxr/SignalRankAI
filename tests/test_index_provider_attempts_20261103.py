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


def test_a_provider_in_rate_limit_cooldown_does_not_use_an_attempt(monkeypatch):
    """Forex, 3 Nov: both attempts went to twelvedata (cooldown) and tiingo (429); yfinance never ran."""
    from data import providers

    monkeypatch.setenv("FX_MARKET_DATA_PROVIDERS", "twelvedata,tiingo,yfinance")
    monkeypatch.delenv("OHLC_FX_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", raising=False)
    monkeypatch.delenv("OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", raising=False)
    monkeypatch.setattr(providers, "_PROVIDER_COOLDOWN", {})
    fx = [("twelvedata_connector", object()), ("tiingo_connector", object()), ("yfinance_connector", object())]
    ordered = fetcher._ordered_provider_candidates(fx, asset_kind="fx", timeframe="1h", asset="EURUSD")
    assert [name for name, _ in ordered] == ["twelvedata_connector", "tiingo_connector"]
    providers._set_cooldown("twelvedata", 600)
    ordered = fetcher._ordered_provider_candidates(fx, asset_kind="fx", timeframe="1h", asset="EURUSD")
    assert [name for name, _ in ordered] == ["tiingo_connector", "yfinance_connector"]
    providers._set_cooldown("tiingo", 600)
    providers._set_cooldown("yahoo", 600)
    # Everything cooling down: keep the configured list rather than fetch nothing.
    ordered = fetcher._ordered_provider_candidates(fx, asset_kind="fx", timeframe="1h", asset="EURUSD")
    assert [name for name, _ in ordered] == ["twelvedata_connector", "tiingo_connector"]


def test_tiingo_records_a_cooldown_on_429(monkeypatch):
    from data import providers

    monkeypatch.setattr(providers, "_PROVIDER_COOLDOWN", {})
    monkeypatch.delenv("TIINGO_RATE_LIMIT_COOLDOWN_SECONDS", raising=False)
    assert providers._rate_limit_cooldown_seconds("tiingo", status_code=429) == 15 * 60
    assert providers._maybe_apply_rate_limit_cooldown("tiingo", status_code=429)
    assert providers._is_cooldown_active("tiingo")
    assert providers._rate_limit_cooldown_seconds("tiingo", status_code=500) is None
