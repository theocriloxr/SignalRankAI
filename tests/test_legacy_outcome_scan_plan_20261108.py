"""The bot's candle-scan outcome writer follows the published plan (8 Nov 2026).

Owner report, 4 Nov: BCHUSDT 5m (delivered 06:50 UTC, card "Expires 23h 59m")
got "Entry Not Triggered ... before the signal expired" at 06:55. The bot's
``compute_outcomes_best_effort`` wrote ``missed`` whenever the bars since
creation had not touched entry. The same scan kept the original stop after
TP1 (a pullback became -1R, not a protected exit), kept scanning after TP3,
and fell back to other timeframes' candles.
"""
from pathlib import Path

from signalrank_telegram.bot import evaluate_signal_outcome_from_candles

BOT = Path(__file__).resolve().parents[1] / "signalrank_telegram" / "bot.py"


def _eval(candles, levels=(0.917334,), entry=0.8976, stop=0.8921, direction="long"):
    return evaluate_signal_outcome_from_candles(entry=entry, stop_loss=stop, tp_levels=list(levels),
                                                direction=direction, candles=candles)


def test_pullback_to_entry_after_tp1_is_a_protected_exit_not_a_loss():
    # SUIUSDT 4-5 Nov: filled, TP1 0.917334, then back through entry (not the stop).
    result = _eval([
        {"timestamp": 1, "high": 0.8980, "low": 0.8970},
        {"timestamp": 2, "high": 0.9180, "low": 0.9000},
        {"timestamp": 3, "high": 0.9000, "low": 0.8950},
    ])
    assert result["status"] == "partial_win_be" and result["max_tp_hit"] == 1


def test_tp3_is_final_even_if_price_later_falls_through_the_stop():
    result = _eval([
        {"timestamp": 1, "high": 101.0, "low": 99.0},
        {"timestamp": 2, "high": 106.5, "low": 100.5},
        {"timestamp": 3, "high": 100.0, "low": 90.0},
    ], levels=(102.0, 104.0, 106.0), entry=100.0, stop=95.0)
    assert result["status"] == "tp3"


def test_stop_before_any_target_is_still_a_loss():
    result = _eval([
        {"timestamp": 1, "high": 0.8980, "low": 0.8970},
        {"timestamp": 2, "high": 0.8990, "low": 0.8900},
    ])
    assert result["status"] == "sl"


def test_short_protected_exit():
    result = _eval([
        {"timestamp": 1, "high": 100.5, "low": 99.5},
        {"timestamp": 2, "high": 99.0, "low": 97.5},
        {"timestamp": 3, "high": 100.2, "low": 99.0},
    ], levels=(98.0, 96.0, 94.0), entry=100.0, stop=102.0, direction="short")
    assert result["status"] == "partial_win_be"


def test_writer_waits_for_expiry_and_uses_only_the_signal_timeframe():
    source = BOT.read_text(encoding="utf-8")
    start = source.index("    def compute_outcomes_best_effort():")
    body = source[start: source.index("    def _in_quiet_hours(", start)]
    assert "if now < expires_at:\n                            continue" in body
    assert "alt_tfs" not in body
    assert "calculate_partial_exit_result" in body
    assert '"partial_win_be", "tp3", "tp", "sl"' in body
