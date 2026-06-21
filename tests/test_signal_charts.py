from signalrank_telegram.signal_charts import render_signal_chart


def test_render_signal_chart_returns_png_bytes():
    candles = []
    price = 100.0
    for idx in range(30):
        open_price = price
        close_price = price + 0.4
        high_price = close_price + 0.2
        low_price = open_price - 0.2
        candles.append(
            {
                "timestamp": 1700000000000 + (idx * 60000),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )
        price = close_price

    signal = {
        "signal_id": "sig-chart-1",
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "direction": "long",
        "entry": 104.0,
        "stop_loss": 101.0,
        "take_profit": [108.0, 112.0],
        "rr_ratio": 2.0,
        "score": 88,
        "regime": "TRENDING",
        "strategy_name": "breakout",
    }

    image = render_signal_chart(signal, candles=candles)
    assert image is not None
    assert image.getbuffer().nbytes > 0
    assert image.name.endswith(".png")