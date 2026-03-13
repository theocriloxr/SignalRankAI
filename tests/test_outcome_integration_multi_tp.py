from signalrank_telegram.bot import evaluate_signal_outcome_from_candles


def test_long_signal_progresses_to_tp3_with_synthetic_candles():
    entry = 100.0
    sl = 95.0
    tp_levels = [102.0, 104.0, 106.0]
    candles: list[dict[str, object]] = [
        {"timestamp": 1, "high": 101.0, "low": 99.0},   # fills entry
        {"timestamp": 2, "high": 102.2, "low": 100.5}, # tp1
        {"timestamp": 3, "high": 104.1, "low": 101.0}, # tp2
        {"timestamp": 4, "high": 106.5, "low": 103.8}, # tp3
    ]

    result: dict[str, object] = evaluate_signal_outcome_from_candles(
        entry=entry,
        stop_loss=sl,
        tp_levels=tp_levels,
        direction="long",
        candles=candles,
    )

    assert result["entry_filled"] is True
    assert result["max_tp_hit"] == 3
    assert result["status"] == "tp3"


def test_long_signal_hits_sl_after_entry_with_synthetic_candles():
    entry = 100.0
    sl = 95.0
    tp_levels = [102.0, 104.0, 106.0]
    candles: list[dict[str, object]] = [
        {"timestamp": 1, "high": 100.4, "low": 99.7},  # fills entry
        {"timestamp": 2, "high": 101.2, "low": 94.8},  # hits SL
        {"timestamp": 3, "high": 106.5, "low": 96.0},  # ignored after SL outcome
    ]

    result: dict[str, object] = evaluate_signal_outcome_from_candles(
        entry=entry,
        stop_loss=sl,
        tp_levels=tp_levels,
        direction="long",
        candles=candles,
    )

    assert result["entry_filled"] is True
    assert result["status"] == "sl"
