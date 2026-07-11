from db.pg_features import compute_signal_fingerprint


def test_signal_fingerprint_includes_candle_timestamp() -> None:
    base_signal = {
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": [105.0, 110.0],
        "strategy_group": "momentum",
        "strategy_name": "breakout",
        "candle_timestamp": "2024-01-01T00:00:00",
    }
    same_candle = dict(base_signal)
    next_candle = dict(base_signal, candle_timestamp="2024-01-01T01:00:00")

    assert compute_signal_fingerprint(base_signal) == compute_signal_fingerprint(same_candle)
    assert compute_signal_fingerprint(base_signal) != compute_signal_fingerprint(next_candle)
