"""Post-release range breakout (strategies/news_setups.py, 23 Nov 2026)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from strategies import news_setups as ns

EVENT = datetime(2026, 11, 24, 13, 30, tzinfo=timezone.utc)


def _bars(after_closes, *, spike=(1.1000, 1.1060, 1.0995, 1.1050)):
    """5m bars: 40 quiet bars, a 3-bar release window, then the given closes."""
    out, t = [], EVENT - timedelta(minutes=5 * 40)
    price = 1.1000
    for _ in range(40):
        out.append({"timestamp": int(t.timestamp() * 1000), "open": price, "high": price + 0.0015,
                    "low": price - 0.0015, "close": price})
        t += timedelta(minutes=5)
    o, h, l, c = spike
    for i in range(3):
        out.append({"timestamp": int(t.timestamp() * 1000), "open": o if i == 0 else c, "high": h, "low": l,
                    "close": c})
        t += timedelta(minutes=5)
    for close in after_closes:
        out.append({"timestamp": int(t.timestamp() * 1000), "open": close - 0.0002, "high": close + 0.0002,
                    "low": close - 0.0004, "close": close})
        t += timedelta(minutes=5)
    return out, t


def test_first_close_above_the_release_range_is_a_long():
    bars, t = _bars([1.1045, 1.1052, 1.1066])
    setup = ns.release_range_breakout(bars, EVENT, tf_seconds=300, now=t)
    assert setup and setup["direction"] == "LONG"
    assert abs(setup["stop"] - (1.1060 + 1.0995) / 2) < 1e-9
    risk = setup["entry"] - setup["stop"]
    assert abs(setup["targets"][0] - (setup["entry"] + 1.5 * risk)) < 1e-9


def test_not_the_first_close_beyond_is_skipped():
    bars, t = _bars([1.1066, 1.1050, 1.1068])
    assert ns.release_range_breakout(bars, EVENT, tf_seconds=300, now=t) is None


def test_against_the_release_move_is_skipped():
    bars, t = _bars([1.1000, 1.0990], spike=(1.1050, 1.1060, 1.0995, 1.1000))
    # release window closed down; a close below the range is continuation, above would be a fade
    setup = ns.release_range_breakout(bars, EVENT, tf_seconds=300, now=t)
    assert setup and setup["direction"] == "SHORT"
    bars2, t2 = _bars([1.1066], spike=(1.1050, 1.1060, 1.0995, 1.1000))
    assert ns.release_range_breakout(bars2, EVENT, tf_seconds=300, now=t2) is None


def test_ignored_release_and_too_late_are_skipped():
    quiet, t = _bars([1.1006], spike=(1.1000, 1.1003, 1.0998, 1.1002))
    assert ns.release_range_breakout(quiet, EVENT, tf_seconds=300, now=t) is None
    bars, _t = _bars([1.1066])
    assert ns.release_range_breakout(bars, EVENT, tf_seconds=300, now=EVENT + timedelta(hours=4)) is None


def test_wired_into_strategy_runner():
    from pathlib import Path

    assert "news_setup_candidates" in Path("strategies/__init__.py").read_text()
