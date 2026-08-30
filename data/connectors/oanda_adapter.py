"""OANDA practice/live market-data compatibility adapter.

The underlying provider already uses the configured practice endpoint by
default. This wrapper makes it available to the canonical key-aware registry.
"""
from __future__ import annotations
from typing import Any, Dict, List
from data.providers import fetch_oanda_candles


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    del timeout
    rows = fetch_oanda_candles(symbol, timeframe) or []
    return list(rows)[-max(1, int(limit or 200)):]
