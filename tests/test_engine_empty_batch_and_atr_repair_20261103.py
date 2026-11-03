"""Owner decisions, 3 Nov 2026: pause after empty engine batches; ATR stop repair runs.

Both were findings left open on 1 Nov (docs/release/RELEASE_BLOCKERS.md):
a batch with no candidates skipped the end-of-cycle pause, and the
SignalController ATR stop repair never ran (missing import, plain function
passed to run_sync).
"""
from pathlib import Path

import pytest

import engine.core as core
from engine.signal_controller import SignalController

ROOT = Path(__file__).resolve().parents[1]


def test_empty_batch_pause_is_bounded(monkeypatch):
    monkeypatch.delenv("ENGINE_EMPTY_CYCLE_SLEEP_SECONDS", raising=False)
    assert core._empty_batch_sleep_seconds(30) == 5.0
    monkeypatch.setenv("ENGINE_EMPTY_CYCLE_SLEEP_SECONDS", "30")
    assert core._empty_batch_sleep_seconds(30) == 30.0
    monkeypatch.setenv("ENGINE_EMPTY_CYCLE_SLEEP_SECONDS", "999")
    assert core._empty_batch_sleep_seconds(30) == 30.0
    monkeypatch.setenv("ENGINE_EMPTY_CYCLE_SLEEP_SECONDS", "0")
    assert core._empty_batch_sleep_seconds(30) == 1.0
    monkeypatch.setenv("ENGINE_EMPTY_CYCLE_SLEEP_SECONDS", "nan-ish")
    assert core._empty_batch_sleep_seconds(30) == 5.0


def test_empty_batch_sleeps_before_continuing():
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    block = source[source.index('logger.info("[delivery_skipped] reason=no_candidates'):]
    block = block[:block.index("continue") + len("continue")]
    assert "time.sleep(_empty_batch_sleep_seconds(cycle_sleep_seconds))" in block


def _candles(n=40, base=11.0, rng=0.2):
    out = []
    for i in range(n):
        out.append({"open": base, "high": base + rng / 2, "low": base - rng / 2, "close": base})
    return out


@pytest.fixture
def market(monkeypatch):
    calls = []

    async def fake_fetch(asset, tfs, **_kw):
        calls.append((asset, list(tfs)))
        return {tfs[0]: {"candles": _candles()}}

    monkeypatch.setattr("data.market_data.fetch_market_data_cached", fake_fetch)
    monkeypatch.delenv("SIGNAL_ATR_STOP_REPAIR_ENABLED", raising=False)
    return calls


def _sig(entry, stop, direction="long", tps=(11.5, 12.0, 12.5), asset="LINKUSDT"):
    return {"asset": asset, "timeframe": "1d", "direction": direction, "entry": entry, "stop_loss": stop,
            "take_profit": list(tps), "strategy_name": "ATR Breakout"}


def test_stop_equal_to_entry_is_repaired_from_atr(market):
    out = SignalController().normalize_signals([_sig(11.005, 11.005)])[0]
    assert market == [("LINKUSDT", ["1d"])]
    assert out["atr_stop_repaired"] is True
    atr = 0.2
    assert out["stop_loss"] < 11.005
    assert 11.005 - out["stop_loss"] <= 2 * atr + 1e-9
    assert out["take_profit"] == pytest.approx([11.005 + 2 * atr, 11.005 + 3 * atr, 11.005 + 5 * atr])
    assert out["atr_stop_repair"]["original_stop_loss"] == 11.005
    assert out["rr_ratio"] > 0


def test_short_with_stop_on_the_wrong_side_is_repaired(market):
    out = SignalController().normalize_signals([_sig(11.0, 10.99, "short", (10.5, 10.0, 9.5))])[0]
    assert out["atr_stop_repaired"] is True
    assert out["stop_loss"] > 11.0
    assert all(t < 11.0 for t in out["take_profit"])


def test_tight_but_normal_stop_is_kept(market):
    # 0.2 % stop on an asset whose ATR is 0.05: 0.022 >= 0.25 * ATR -> kept.
    async def calm(asset, tfs, **_kw):
        return {tfs[0]: {"candles": _candles(rng=0.05)}}

    import data.market_data as md
    md_fetch = md.fetch_market_data_cached
    md.fetch_market_data_cached = calm
    try:
        sig = _sig(11.0, 10.978, tps=(11.05, 11.1, 11.2), asset="EURUSD")
        out = SignalController().normalize_signals([sig])[0]
    finally:
        md.fetch_market_data_cached = md_fetch
    assert "atr_stop_repaired" not in out
    assert out["stop_loss"] == 10.978


def test_wide_stop_never_fetches(market):
    out = SignalController().normalize_signals([_sig(11.0, 10.5)])[0]
    assert market == []
    assert out["stop_loss"] == 10.5


def test_repair_can_be_switched_off(market, monkeypatch):
    monkeypatch.setenv("SIGNAL_ATR_STOP_REPAIR_ENABLED", "0")
    out = SignalController().normalize_signals([_sig(11.005, 11.005)])[0]
    assert out["stop_loss"] == 11.005


def test_too_few_candles_leaves_the_candidate_for_validation(monkeypatch):
    async def short(asset, tfs, **_kw):
        return {tfs[0]: {"candles": _candles(n=10)}}

    monkeypatch.setattr("data.market_data.fetch_market_data_cached", short)
    out = SignalController().normalize_signals([_sig(11.005, 11.005)])[0]
    assert out["stop_loss"] == 11.005
