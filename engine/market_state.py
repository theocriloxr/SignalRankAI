"""Aggregate market data (candles, indicators, optional ML) for strategies.

This module provides a small, testable abstraction used by strategies to
request recent candles and derived indicators. It's intentionally small and
defensive: it prefers `data.fetcher.fetch_market_data` which already validates
candles and computes indicators.
"""
from typing import Dict, Iterable, List, Optional, Any

import asyncio

from data.fetcher import fetch_market_data
from core.validators import validate_candles
from utils.async_runner import run_sync

try:  # ml scorer optional
    from engine import ml as ml_module
except Exception:
    ml_module = None


async def get_market_state(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:
    """Async variant: fetch market data (runs blocking fetch in thread) and build state.

    Use `asyncio.to_thread` to call the synchronous `fetch_market_data` safely from
    async contexts. For sync callers, use `get_market_state_sync` below.
    """
    tf_list: List[str] = list(timeframes or [])
    out: Dict[str, Any] = {"asset": asset, "timeframes": {}}
    if not tf_list:
        return out

    # Run blocking fetch in thread
    market = await asyncio.to_thread(fetch_market_data, asset, tf_list)

    for tf in tf_list:
        entry = market.get(tf)
        if not entry:
            continue
        candles = entry.get("candles") or []
        indicators = entry.get("indicators") or {}

        if not validate_candles(candles):
            continue

        last = candles[-1] if candles else None
        last_close = None
        last_ts = None
        if last:
            last_close = last.get("close") or last.get("close_price")
            last_ts = last.get("timestamp") or last.get("time")

        tf_state: Dict[str, Any] = {
            "candles": candles,
            "indicators": indicators,
            "last_close": last_close,
            "last_timestamp": last_ts,
        }

        if include_ml and ml_module is not None and hasattr(ml_module, "score_signal"):
            try:
                probe = {
                    "asset": asset,
                    "timeframe": tf,
                    "entry": float(last_close) if last_close is not None else 0.0,
                    "stop_loss": float(last_close) if last_close is not None else 0.0,
                    "score": 0.0,
                }
                # ML scorer is sync; run in thread
                prob = await asyncio.to_thread(ml_module.score_signal, probe)
                tf_state["ml_score"] = prob
            except Exception:
                tf_state["ml_score"] = None

        out["timeframes"][tf] = tf_state

    return out


def get_market_state_sync(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:
    """Sync wrapper for code that expects blocking call; runs async get_market_state safely."""
    return run_sync(get_market_state(asset, timeframes, include_ml=include_ml))
