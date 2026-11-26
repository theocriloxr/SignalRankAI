"""OANDA practice API covers index, oil and metal CFDs in real time (26 Nov 2026)."""
from __future__ import annotations

from pathlib import Path

from services.asset_mapper import map_symbol


def test_oanda_maps_index_and_commodity_cfds():
    assert map_symbol("GER40", "oanda") == "DE30_EUR"
    assert map_symbol("UK100", "oanda") == "UK100_GBP"
    assert map_symbol("US500", "oanda") == "SPX500_USD"
    assert map_symbol("NAS100", "oanda") == "NAS100_USD"
    assert map_symbol("JP225", "oanda") == "JP225_USD"
    assert map_symbol("HK50", "oanda") == "HK33_HKD"
    assert map_symbol("WTI", "oanda") == "WTICO_USD" and map_symbol("BRENT", "oanda") == "BCO_USD"
    assert map_symbol("XAUUSD", "oanda") == "XAU_USD" and map_symbol("EURUSD", "oanda") == "EUR_USD"
    assert map_symbol("AAPL", "oanda") is None  # no single-stock CFDs: never a wrong instrument


def test_index_quotes_route_to_oanda_when_configured(monkeypatch):
    from data import get_live_price as glp

    monkeypatch.setenv("OANDA_API_KEY", "x")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "y")
    assert "oanda" in glp._get_providers_for_asset("GER40")
    monkeypatch.delenv("OANDA_API_KEY")
    assert "oanda" not in glp._get_providers_for_asset("GER40")


def test_oanda_candles_use_the_mapped_instrument(monkeypatch):
    from data import providers

    seen = {}

    class R:
        ok = True
        status_code = 200

        def json(self):
            return {"candles": []}

    def fake_get(url, headers=None, params=None, timeout=None, **k):
        seen["url"] = url
        return R()

    monkeypatch.setenv("OANDA_API_KEY", "x")
    monkeypatch.setattr(providers, "_is_cooldown_active", lambda name: False)
    import requests
    monkeypatch.setattr(requests, "get", fake_get)
    providers.fetch_oanda_candles("GER40", "15m")
    assert "/instruments/DE30_EUR/candles" in seen.get("url", "")


def test_track_record_counts_only_signals_actually_delivered():
    sql = Path("services/public_track_record.py").read_text()
    assert "d.delivered_at IS NOT NULL" not in sql and "d.sent_ok IS TRUE" in sql
