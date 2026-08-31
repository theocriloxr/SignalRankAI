from __future__ import annotations

from datetime import datetime, timezone

from strategies import _certified_strategy_market_data


def _candles(count: int = 40) -> list[dict]:
    start = int(datetime(2026, 8, 24, tzinfo=timezone.utc).timestamp())
    return [
        {
            "timestamp": (start + index * 3600) * 1000,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 10.0,
        }
        for index in range(count)
    ]


def test_invalid_timeframe_never_reaches_any_strategy_family() -> None:
    valid = _candles()
    invalid = _candles()
    invalid[20]["high"] = 90.0
    result = _certified_strategy_market_data(
        "BTCUSDT",
        "crypto",
        {
            "1h": {"candles": valid, "indicators": {}, "provider": "test"},
            "4h": {"candles": invalid, "indicators": {}, "provider": "test"},
            "_macro": {"risk": "neutral"},
        },
    )
    assert "1h" in result
    assert "4h" not in result
    assert "_macro" in result
