"""Manual live strategy smoke test.

Run with:
    RUN_LIVE_DATA_TESTS=1 python strategy_live_smoke.py
"""

import os


def main() -> int:
    if os.getenv("RUN_LIVE_DATA_TESTS", "0").strip().lower() not in {"1", "true", "yes"}:
        print("Set RUN_LIVE_DATA_TESTS=1 to run live provider strategy smoke.")
        return 0

    os.environ["CANDLE_REQUEST_CACHE_TTL_SECONDS"] = "0.1"

    from data.fetcher import get_candles
    from data.indicators import calculate_indicators
    from strategies import run_all_strategies
    from strategies.imp import institutional_momentum_pulse_strategies
    from strategies.trend import trend_strategies

    asset = "BTCUSDT"
    timeframe = "1h"
    candles = get_candles(asset, timeframe)
    if not candles:
        print("No candles returned")
        return 1

    indicators = calculate_indicators(candles)
    market_data = {timeframe: {"candles": candles, "indicators": indicators}}

    print(f"IMP signals: {len(list(institutional_momentum_pulse_strategies(asset, market_data)))}")
    print(f"Trend signals: {len(list(trend_strategies(asset, timeframe, market_data[timeframe])))}")
    print(f"All signals: {len(run_all_strategies(asset, market_data, 'TRENDING'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
