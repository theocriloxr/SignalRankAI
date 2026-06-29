"""Quick synthetic-data test for signal generation."""

import pandas as pd


def test_synthetic_signal_generation_smoke():
    from data.indicators import calculate_indicators
    from strategies import run_all_strategies

    candles = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=100, freq="h"),
            "open": [50000 + i * 10 for i in range(100)],
            "high": [50050 + i * 10 for i in range(100)],
            "low": [49950 + i * 10 for i in range(100)],
            "close": [50000 + i * 10 for i in range(100)],
            "volume": [1000000 for _ in range(100)],
        }
    )

    candle_rows = candles.to_dict("records")
    indicators = calculate_indicators(candle_rows)
    market_data = {"1h": {"candles": candle_rows, "indicators": indicators}}
    signals = run_all_strategies("BTCUSDT", market_data, "bullish")

    assert isinstance(signals, list)
