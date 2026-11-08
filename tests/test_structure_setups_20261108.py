"""Chart-structure setups learned from the owner's strategy deck (8 Nov 2026).

The deck (466 annotated TradingView photos with MT5 position lists) trades
zone flip retests, trendline break-retests and channel/triangle breaks with
stops just beyond the structure and targets at the next swings. The family is
additive and shadow-only by default.
"""
import math
from pathlib import Path

import pytest

from strategies import structure_setups as ss
from strategies.structure_setups import _ladder, detect_setups, structure_setup_candidates

ROOT = Path(__file__).resolve().parents[1]


def bar(o, c, wick=0.3):
    return {"open": o, "close": c, "high": max(o, c) + wick, "low": min(o, c) - wick}


def leg(out, a, b, n):
    p = out[-1]["close"] if out else a
    for k in range(1, n + 1):
        c = a + (b - a) * k / n
        out.append({"open": p, "close": c, "high": max(p, c) + 0.15, "low": min(p, c) - 0.15})
        p = c


def flip_long():
    b, p = [], 100.0
    for i in range(70):
        c = 100 + (0.5 if i % 2 else -0.5)
        b.append(bar(p, c)); p = c
    b += [bar(100.5, 101.5), bar(101.5, 102.5), bar(102.5, 102.0, 0.2)]
    b[-2]["high"] = 103.0
    b += [bar(102.0, 101.0), bar(101.0, 100.4), bar(100.4, 100.8), bar(100.8, 101.0), bar(101.0, 104.5)]
    b += [bar(104.5, 106.0), bar(106.0, 107.2), bar(107.2, 106.0), bar(106.0, 104.8), bar(104.8, 104.2)]
    s = bar(104.2, 103.9); s["low"] = 102.95; b.append(s)
    b.append(bar(103.9, 104.0))
    return b


def channel():
    out, p = [], 100.0
    for i in range(100):
        c = 100 + 3 * math.sin(i * 2 * math.pi / 20)
        out.append({"open": p, "close": c, "high": max(p, c) + 0.1, "low": min(p, c) - 0.1}); p = c
    out.append({"open": p, "close": p + 4.5, "high": p + 4.7, "low": p - 0.1})
    out.append({"open": p + 4.5, "close": p + 4.6, "high": p + 4.8, "low": p + 4.3})
    return out


def rising_then_break():
    out = []
    leg(out, 100, 100, 30)
    leg(out, 100, 106, 8); leg(out, 106, 101, 8); leg(out, 101, 108, 8); leg(out, 108, 103, 8); leg(out, 103, 109, 6)
    leg(out, 109, 101.5, 6); leg(out, 101.5, 103.6, 4)
    out[-1]["high"] = out[-1]["close"] + 1.4
    out.append({"open": out[-1]["close"], "close": out[-1]["close"] - 0.2, "high": out[-1]["close"],
                "low": out[-1]["close"] - 0.4})
    return out


def _one(candles, name):
    found = [s for s in detect_setups(candles) if s["strategy_name"] == name]
    assert len(found) == 1, detect_setups(candles)
    return found[0]


def test_zone_flip_retest_long():
    s = _one(flip_long(), "Zone Flip Retest")
    assert s["direction"] == "LONG" and s["entry"] == pytest.approx(103.9)
    assert s["stop"] < s["zone_low"] and s["targets"][0] == pytest.approx(107.5)


def test_trendline_break_retest_short():
    s = _one(rising_then_break(), "Trendline Break Retest")
    assert s["direction"] == "SHORT" and s["stop"] > s["entry"]
    assert s["targets"][0] == pytest.approx(100.85)  # the swing low the line was drawn through


def test_channel_break_long_with_measured_targets():
    s = _one(channel(), "Channel Break")
    assert s["direction"] == "LONG" and s["channel_shape"] == "channel"
    risk = s["entry"] - s["stop"]
    assert all(t - s["entry"] >= risk for t in s["targets"]) and s["targets"] == sorted(s["targets"])


def test_flat_market_and_short_history_give_nothing():
    flat = [bar(100.0, 100.0, 0.1) for _ in range(120)]
    assert detect_setups(flat) == [] and detect_setups(channel()[:40]) == []


def test_targets_closer_than_1r_are_skipped_never_invented():
    assert _ladder(100.0, 2.0, [101.0, 103.0, 105.0], True) == [103.0, 105.0]
    assert _ladder(100.0, 2.0, [101.0], True) == []


def test_modes(monkeypatch):
    recorded = []
    monkeypatch.setattr(ss, "_record_shadow", lambda c: recorded.append(c))
    monkeypatch.setattr(ss, "_seen", {})
    monkeypatch.delenv("STRUCTURE_SETUPS_MODE", raising=False)
    assert structure_setup_candidates("XAUUSD", "15m", {"candles": channel()}) == []
    assert recorded and recorded[0]["asset"] == "XAUUSD"
    monkeypatch.setattr(ss, "_seen", {})
    monkeypatch.setenv("STRUCTURE_SETUPS_MODE", "live")
    live = structure_setup_candidates("XAUUSD", "15m", {"candles": channel()})
    assert live and live[0]["strategy_group"] == "structure_setups"
    monkeypatch.setenv("STRUCTURE_SETUPS_MODE", "off")
    assert structure_setup_candidates("XAUUSD", "15m", {"candles": channel()}) == []
    monkeypatch.setenv("STRUCTURE_SETUPS_MODE", "live")
    assert structure_setup_candidates("XAUUSD", "1d", {"candles": channel()}) == []  # intraday family


def test_registered_after_discovered_strategies():
    source = (ROOT / "strategies" / "__init__.py").read_text(encoding="utf-8")
    assert '_run_group("structure_setups", lambda: structure_setup_candidates(asset, timeframe, data))' in source
