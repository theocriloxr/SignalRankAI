"""FundedNext focus (owner request, 9 Nov 2026)."""
from __future__ import annotations

from pathlib import Path

from core import broker_universe as bu


def test_fundednext_assets_come_first_and_are_always_included(monkeypatch):
    monkeypatch.delenv("BROKER_UNIVERSE_ASSETS", raising=False)
    monkeypatch.setenv("BROKER_UNIVERSE_PROFILE", "fundednext")
    ordered = bu.prioritize(["TSLA", "SOLUSDT", "XAUUSD"])
    assert ordered[0] == "XAUUSD" and "US30" in ordered and ordered[-2:] == ["TSLA", "SOLUSDT"]
    assert bu.is_broker_asset("BTCUSDT") and not bu.is_broker_asset("TSLA")
    monkeypatch.setenv("BROKER_UNIVERSE_STRICT", "1")
    assert "TSLA" not in bu.prioritize(["TSLA", "XAUUSD"])


def test_override_and_off(monkeypatch):
    monkeypatch.setenv("BROKER_UNIVERSE_ASSETS", "EURUSD,XAUUSD")
    assert bu.broker_assets() == ("EURUSD", "XAUUSD")
    monkeypatch.setenv("BROKER_UNIVERSE_PROFILE", "off")
    assert bu.prioritize(["TSLA"]) == ["TSLA"] and not bu.is_broker_asset("EURUSD")


def test_engine_reserves_a_batch_share_for_broker_assets():
    source = (Path(__file__).resolve().parents[1] / "engine" / "core.py").read_text("utf-8")
    assert "_broker_queue = AssetCycleQueue()" in source
    assert 'BROKER_UNIVERSE_SHARE' in source and "_broker_prioritize(assets)" in source


def test_card_says_when_the_instrument_is_on_fundednext(monkeypatch):
    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    monkeypatch.delenv("BROKER_UNIVERSE_ASSETS", raising=False)
    monkeypatch.setenv("BROKER_UNIVERSE_PROFILE", "fundednext")
    card = format_vip_signal(dict(asset="XAUUSD", direction="long", entry=4100, stop_loss=4080, take_profit=[4150],
                                  timeframe="1h", strategy_name="ADX Trend", score=70, signal_id="x"))
    assert "Tradable on FundedNext" in card
