from typing import Sequence, Dict, Any

from prometheus_client import Counter

data_validation_failures_total = Counter(
    "data_validation_failures_total",
    "Number of times incoming candlestick/news data failed validation",
)


def validate_candles(candles: Sequence[Dict[str, Any]]) -> bool:
    """Basic validation for candle arrays.

    Returns True when candles look valid, False otherwise and increments
    the Prometheus counter on failure.
    """
    if not candles:
        data_validation_failures_total.inc()
        return False
    # Expect dicts with numeric OHLC
    for c in candles:
        if not isinstance(c, dict):
            data_validation_failures_total.inc()
            return False
        for key in ("time", "open", "high", "low", "close"):
            if key not in c:
                data_validation_failures_total.inc()
                return False
    return True
