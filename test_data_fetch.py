"""Diagnostic test for data fetching and indicators."""

import os

import pytest


def _fetch_sample_candles():
    from data.fetcher import get_candles

    return get_candles("BTCUSDT", "1h")


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATA_TESTS", "0").strip().lower() not in {"1", "true", "yes"},
    reason="live market-data smoke test requires RUN_LIVE_DATA_TESTS=1",
)
def test_live_data_fetch_and_indicators():
    candles = _fetch_sample_candles()

    assert candles

    from data.indicators import calculate_indicators

    indicators = calculate_indicators(candles)
    assert indicators
    assert "close_price" in indicators


if __name__ == "__main__":
    candles = _fetch_sample_candles()
    print(f"Got {len(candles) if candles else 0} candles")
    if candles:
        print(f"First candle timestamp: {candles[0].get('timestamp')}")
        print(f"Last candle: close={candles[-1].get('close')}")
    else:
        print("No candles returned")
