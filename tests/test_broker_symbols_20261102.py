"""Broker symbol resolution for MT4/MT5 brokers (2 Nov 2026)."""
from __future__ import annotations

from services.broker_symbols import resolve_from_list

EXNESS_STANDARD = ["EURUSDm", "GBPUSDm", "XAUUSDm", "USTECm", "US500m", "US30m", "DE30m", "USOILm", "UKOILm",
                   "BTCUSDm", "AAPLm", "Vm", "VIXm"]
ICM_STYLE = ["EURUSD", "EURUSD.r", "XAUUSD", "US500.cash", "GER40.cash", "XTIUSD", "AAPL.NAS", "#V", "VOD.L"]


def test_exness_suffixes():
    assert resolve_from_list("EURUSD", EXNESS_STANDARD) == "EURUSDm"
    assert resolve_from_list("XAUUSD", EXNESS_STANDARD) == "XAUUSDm"
    assert resolve_from_list("NAS100", EXNESS_STANDARD) == "USTECm"
    assert resolve_from_list("GER40", EXNESS_STANDARD) == "DE30m"
    assert resolve_from_list("WTI", EXNESS_STANDARD) == "USOILm"
    assert resolve_from_list("V", EXNESS_STANDARD) == "Vm"


def test_exact_name_wins_and_separators():
    assert resolve_from_list("EURUSD", ICM_STYLE) == "EURUSD"
    assert resolve_from_list("US500", ICM_STYLE) == "US500.cash"
    assert resolve_from_list("WTI", ICM_STYLE) == "XTIUSD"
    assert resolve_from_list("AAPL", ICM_STYLE) == "AAPL.NAS"
    assert resolve_from_list("V", ICM_STYLE) == "#V"


def test_no_false_matches():
    assert resolve_from_list("V", ["VIX", "VOD"]) is None
    assert resolve_from_list("US30", ["US3000"]) is None
    assert resolve_from_list("EURUSD", ["EURUSDT"]) is None  # crypto pair, not a suffix
    assert resolve_from_list("EURUSD", ["EURUSD.a", "EURUSD.b"]) is None  # ambiguous
    assert resolve_from_list("NVDA", []) is None
