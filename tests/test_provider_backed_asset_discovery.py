from __future__ import annotations

from types import SimpleNamespace

import data.pair_discovery as discovery


def _reset_discovery_state() -> None:
    discovery._ASSET_DISCOVERY_PROVENANCE.clear()
    discovery._TWELVEDATA_REFERENCE_CACHE.clear()
    discovery._TWELVEDATA_SYMBOL_PROBE_CACHE.clear()


def test_provider_merge_does_not_lose_slots_to_duplicates() -> None:
    merged = discovery._merge_provider_results(
        [["AAPL", "MSFT", "NVDA"], ["AAPL", "GOOGL", "META"], ["MSFT", "AMZN"]],
        limit=5,
    )
    assert merged == ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def test_twelvedata_catalogue_verifies_configured_fx_and_commodities(monkeypatch) -> None:
    _reset_discovery_state()
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setenv("FX_PAIRS", "EURUSD,GBPUSD")
    monkeypatch.setenv("COMMODITY_TICKERS", "XAUUSD,XAGUSD,WTI,BRENT")
    monkeypatch.setattr(discovery, "_metaapi_symbols", lambda: [])

    def fake_get(url, **kwargs):
        if url.endswith("/forex_pairs"):
            return SimpleNamespace(
                ok=True,
                status_code=200,
                json=lambda: {
                    "status": "ok",
                    "data": [{"symbol": "EUR/USD"}, {"symbol": "GBP/USD"}],
                },
            )
        if url.endswith("/commodities"):
            return SimpleNamespace(
                ok=True,
                status_code=200,
                json=lambda: {
                    "status": "ok",
                    "data": [
                        {"symbol": "XAU/USD"},
                        {"symbol": "XAG/USD"},
                        {"symbol": "WTI/USD"},
                        {"symbol": "XBR/USD"},
                    ],
                },
            )
        raise AssertionError(url)

    monkeypatch.setattr(discovery.requests, "get", fake_get)

    fx = discovery.get_trending_fx_pairs()
    commodities = discovery.get_trending_commodity_tickers()

    assert fx == ["EURUSD", "GBPUSD"]
    assert commodities == ["XAUUSD", "XAGUSD", "WTI", "BRENT"]
    for symbol in fx + commodities:
        assert "twelvedata" in discovery.asset_discovery_provenance(symbol)


def test_twelvedata_catalogue_verifies_manual_stock_allowlist(monkeypatch) -> None:
    _reset_discovery_state()
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setenv("STOCK_TICKERS", "MSFT,NVDA,META")
    monkeypatch.setenv("ASSET_DISCOVERY_MODE", "manual")
    monkeypatch.setattr(discovery, "_metaapi_symbols", lambda: [])

    def fake_get(url, **kwargs):
        assert url.endswith("/stocks")
        return SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {
                "status": "ok",
                "data": [
                    {"symbol": "MSFT", "country": "United States"},
                    {"symbol": "NVDA", "country": "United States"},
                    {"symbol": "META", "country": "United States"},
                ],
            },
        )

    monkeypatch.setattr(discovery.requests, "get", fake_get)

    stocks = discovery.get_trending_stock_tickers(top_n=3)
    assert stocks == ["MSFT", "NVDA", "META"]
    for symbol in stocks:
        assert "twelvedata" in discovery.asset_discovery_provenance(symbol)


def test_twelvedata_catalogue_verifies_configured_indices(monkeypatch) -> None:
    _reset_discovery_state()
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setenv("INDEX_TICKERS", "US500,NAS100,US30,GER40,UK100,JP225")
    monkeypatch.setattr(discovery, "_metaapi_symbols", lambda: [])

    def fake_get(url, **kwargs):
        assert url.endswith("/indices")
        return SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {
                "status": "ok",
                "data": [
                    {"symbol": "SPX", "name": "S&P 500"},
                    {"symbol": "NDX", "name": "Nasdaq 100"},
                    {"symbol": "DJI", "name": "Dow Jones Industrial Average"},
                    {"symbol": "DAX", "name": "DAX"},
                    {"symbol": "FTSE", "name": "FTSE 100"},
                    {"symbol": "N225", "name": "Nikkei 225"},
                ],
            },
        )

    monkeypatch.setattr(discovery.requests, "get", fake_get)

    indices = discovery.get_trending_index_tickers(top_n=6)
    assert indices == ["US500", "NAS100", "US30", "GER40", "UK100", "JP225"]
    for symbol in indices:
        assert "twelvedata" in discovery.asset_discovery_provenance(symbol)


def test_current_twelvedata_canonical_mappings() -> None:
    from services.asset_mapper import map_symbol

    assert map_symbol("JP225", "twelvedata") == "N225"
    assert map_symbol("BRENT", "twelvedata") == "XBR/USD"
