"""Live strategy smoke test."""

import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATA_TESTS", "0").strip().lower() not in {"1", "true", "yes"},
    reason="live strategy smoke test requires RUN_LIVE_DATA_TESTS=1",
)
def test_live_strategies_run_with_market_data():
    os.environ["CANDLE_REQUEST_CACHE_TTL_SECONDS"] = "0.1"

    from data.fetcher import get_candles
    from data.indicators import calculate_indicators
    from strategies import run_all_strategies
    from strategies.imp import institutional_momentum_pulse_strategies
    from strategies.trend import trend_strategies

    asset = "BTCUSDT"
    timeframe = "1h"
    candles = get_candles(asset, timeframe)

    assert candles

    indicators = calculate_indicators(candles)
    market_data = {timeframe: {"candles": candles, "indicators": indicators}}

    imp_signals = list(institutional_momentum_pulse_strategies(asset, market_data))
    trend_signals = list(trend_strategies(asset, timeframe, market_data[timeframe]))
    all_signals = run_all_strategies(asset, market_data, "TRENDING")

    assert isinstance(imp_signals, list)
    assert isinstance(trend_signals, list)
    assert isinstance(all_signals, list)


if __name__ == "__main__":
    raise SystemExit("Run with pytest and RUN_LIVE_DATA_TESTS=1 for live strategy validation.")
