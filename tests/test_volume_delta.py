from engine.signal_analytics import calculate_volume_delta


def _make_candle(open, high, low, close, vol):
    return {"open": open, "high": high, "low": low, "close": close, "volume": vol}


def test_calculate_volume_delta_simple():
    candles = []
    # build 21 candles: previous 20 small vols, last candle large bullish
    for i in range(20):
        candles.append(_make_candle(100, 101, 99, 100, 100))
    candles.append(_make_candle(100, 105, 99, 104, 300))

    stats = calculate_volume_delta(candles, window=20)
    assert stats["avg_volume"] == 100.0
    assert stats["rvol"] == 3.0
    # delta_ratio should be positive because last candle is bullish and large
    assert stats["delta_ratio"] > 0.5
