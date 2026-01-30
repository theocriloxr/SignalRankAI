"""Aggregate market data (candles, indicators, optional ML) for strategies.

This module provides a small, testable abstraction used by strategies to
request recent candles and derived indicators. It's intentionally small and
defensive: it prefers `data.fetcher.fetch_market_data` which already validates
candles and computes indicators.
"""
from typing import Dict, Iterable, List, Optional

from data.fetcher import fetch_market_data
from core.validators import validate_candles

try:
    from engine import ml as ml_module
except Exception:
    ml_module = None


def get_market_state(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, any]:
    """Return market state for `asset` keyed by timeframe.

    Structure:
      {
          "asset": asset,
          "timeframes": {
              "1h": {
                  "candles": [...],
                  "indicators": {...},
                  "last_close": 123.45,
                  "last_timestamp": 1234567890,
                  "ml_score": 0.42,  # optional
              },
              ...
          }
      }
    """
    out: Dict[str, any] = {"asset": asset, "timeframes": {}}
    tf_list: List[str] = list(timeframes or [])
    if not tf_list:
        return out

    market = fetch_market_data(asset, tf_list)
    for tf in tf_list:
        entry = market.get(tf)
        if not entry:
            continue
        candles = entry.get("candles") or []
        indicators = entry.get("indicators") or {}

        # Basic defensive validation: prefer `validate_candles` but allow legacy shapes
        if not validate_candles(candles):
            continue

        # Determine last close and timestamp (support both 'time' and 'timestamp')
        last = candles[-1] if candles else None
        last_close = None
        last_ts = None
        if last:
            last_close = last.get("close") or last.get("close_price")
            last_ts = last.get("timestamp") or last.get("time")

        tf_state: Dict[str, any] = {
            "candles": candles,
            "indicators": indicators,
            "last_close": last_close,
            "last_timestamp": last_ts,
        }

        # Optionally attach ML score via engine.ml.score_signal when available
        if include_ml and ml_module is not None and hasattr(ml_module, "score_signal"):
            try:
                # Build minimal signal-like payload for scoring; keep it lightweight.
                probe = {
                    "asset": asset,
                    "timeframe": tf,
                    "entry": float(last_close) if last_close is not None else 0.0,
                    "stop_loss": float(last_close) if last_close is not None else 0.0,
                    "score": 0.0,
                }
                prob = ml_module.score_signal(probe)
                tf_state["ml_score"] = prob
            except Exception:
                tf_state["ml_score"] = None

        out["timeframes"][tf] = tf_state

    return out
