"""Alpha Vantage compatibility adapter.

Uses the existing normalized legacy implementation while exposing it through
SignalRankAI's connector registry and key-aware provider ordering.
"""
from __future__ import annotations
from typing import Any, Dict, List
from data.providers import fetch_alphavantage_candles


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    del timeout
    rows = fetch_alphavantage_candles(symbol, timeframe) or []
    return list(rows)[-max(1, int(limit or 200)):]
