"""FundedNext MT5 symbol names from the owner's Market Watch screenshots (15 Nov 2026)."""
from __future__ import annotations

import pytest

from core import broker_universe
from core.asset_registry import resolve_asset_spec
from services.asset_mapper import map_symbol
from services.broker_symbols import resolve_from_list

FUNDEDNEXT = ["ADAUSD", "BTCUSD", "DOGUSD", "ETHUSD", "LNKUSD", "LTCUSD", "XLMUSD", "XMRUSD", "XRPUSD",
              "AUS200", "EUSTX50", "FRA40", "GER30", "HK50", "JP225", "NDX100", "NTH25", "SPX500", "SWI20",
              "UK100", "US2000", "US30", "VIX", "UKOUSD", "USOUSD", "XAGUSD", "XAUUSD", "XPTUSD",
              "EURUSD", "USDZAR", "EURHUF", "AAPL", "BMW", "MC"]


@pytest.mark.parametrize("canonical,broker", [
    ("BTCUSDT", "BTCUSD"), ("DOGEUSDT", "DOGUSD"), ("LINKUSDT", "LNKUSD"), ("XMRUSDT", "XMRUSD"),
    ("WTI", "USOUSD"), ("BRENT", "UKOUSD"), ("NAS100", "NDX100"), ("US500", "SPX500"), ("GER40", "GER30"),
    ("EU50", "EUSTX50"), ("NTH25", "NTH25"), ("SWI20", "SWI20"), ("XPTUSD", "XPTUSD"), ("EURHUF", "EURHUF"),
])
def test_orders_use_fundednext_names(canonical, broker):
    assert resolve_from_list(canonical, FUNDEDNEXT) == broker


@pytest.mark.parametrize("raw,canonical,cls", [
    ("DOGUSD", "DOGEUSDT", "crypto"), ("LNKUSD", "LINKUSDT", "crypto"), ("USOUSD", "WTI", "commodity"),
    ("UKOUSD", "BRENT", "commodity"), ("NDX100", "NAS100", "index"), ("EUSTX50", "EU50", "index"),
    ("XPTUSD", "XPTUSD", "commodity"), ("EURHUF", "EURHUF", "forex"), ("USDCNH", "USDCNH", "forex"),
    ("NTH25", "NTH25", "index"), ("BMW", "BMW", "stock"),
])
def test_broker_names_classify(raw, canonical, cls):
    spec = resolve_asset_spec(raw)
    assert (spec.canonical_symbol, spec.asset_class) == (canonical, cls)


def test_eu_shares_use_european_hours_and_yahoo_suffix():
    assert resolve_asset_spec("VOW3").session_calendar == "europe_equity"
    assert map_symbol("BMW", "yfinance") == "BMW.DE"
    assert map_symbol("MC", "yfinance") == "MC.PA"


def test_available_list_is_recognised_but_not_scanned_by_default(monkeypatch):
    monkeypatch.setenv("BROKER_UNIVERSE_PROFILE", "fundednext")
    monkeypatch.delenv("BROKER_UNIVERSE_ASSETS", raising=False)
    monkeypatch.delenv("BROKER_UNIVERSE_SCAN_AVAILABLE", raising=False)
    assert broker_universe.is_broker_asset("USDZAR")
    assert "USDZAR" not in broker_universe.prioritize(["EURUSD"])
    monkeypatch.setenv("BROKER_UNIVERSE_SCAN_AVAILABLE", "1")
    assert "USDZAR" in broker_universe.prioritize(["EURUSD"])
