"""Lifecycle messages describe the stop the user holds and the price really observed (8 Nov 2026).

Owner report, LINKUSDT 5m long (entry 11.069, stop 11.0047, TP1 hit 4 Nov):
on 5 Nov the bot sent "TP Retrace Warning ... close to SL danger zone, Current
10.859 | SL 11.00471" with price already through both stops, then "Protected
Exit ... Observed: 11.069", the entry level shown as if observed.
"""
from pathlib import Path

from engine.realtime_outcome_tracker import _retrace_warning_triggered
from signalrank_telegram.tier_signal_formatter import _ai_review_text

ROOT = Path(__file__).resolve().parents[1]


def test_retrace_zone_is_measured_against_the_protected_stop():
    # Long, entry 11.069, TP1 11.2997: the zone is the last 20 % back to entry.
    assert _retrace_warning_triggered("long", 11.069, 11.2997, 11.10)
    assert not _retrace_warning_triggered("long", 11.069, 11.2997, 11.20)


def test_tracker_skips_the_warning_once_the_protected_stop_is_crossed():
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "protected_stop = float(entry)" in source
    assert "if ml_allows_warning and not crossed and _retrace_warning_triggered(" in source
    assert "direction, protected_stop, best_tp_price, price, zone_pct=zone_pct" in source


def test_protected_exit_names_the_exit_and_only_a_real_market_price():
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "Exit: protected stop at entry <b>{entry_v:g}</b> | Original stop: <b>{sl_v:g}</b>" in source
    assert "Market at detection:" in source


def test_local_review_is_not_presented_as_an_ai_opinion():
    text = _ai_review_text({"ai_review_score": 8.6, "ai_review_reason": "local_ai:confluence_confirms"})
    assert text.startswith("Rule check (AI reviewer unavailable) 8.6/10")
    assert "Local AI" not in text
