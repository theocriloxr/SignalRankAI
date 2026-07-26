"""Marketstack v2 stock/index historical candle adapter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _interval(timeframe: str) -> str | None:
    return {
        "1m": "1min",
        "5m": "5min",
        "10m": "10min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1hour",
        "3h": "3hour",
        "6h": "6hour",
        "12h": "12hour",
        "1d": "24hour",
    }.get(str(timeframe or "").lower())


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    key = str(os.getenv("MARKETSTACK_API_KEY") or "").strip()
    if not key:
        return []
    tf = str(timeframe or "1d").lower()
    count = max(2, min(1000, int(limit or 200)))
    params: dict[str, Any] = {"access_key": key, "symbols": str(symbol).upper().strip(), "limit": count, "sort": "ASC"}
    if tf == "1d":
        endpoint = "https://api.marketstack.com/v2/eod"
        params["date_from"] = (datetime.now(timezone.utc) - timedelta(days=count * 2)).date().isoformat()
    else:
        interval = _interval(tf)
        if not interval:
            return []
        endpoint = "https://api.marketstack.com/v2/intraday"
        params["interval"] = interval
    client = httpx_client.get_client("marketstack")
    if client is None:
        return []
    try:
        response = await client.get(endpoint, params=params, timeout=min(12.0, max(1.0, float(timeout))))
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        items = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(items, dict):
            items = items.get("data")
        if not isinstance(items, list):
            return []
        rows: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                rows.append(
                    {
                        "timestamp": item.get("date") or item.get("timestamp"),
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": float(item.get("volume") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        rows.sort(key=lambda row: str(row["timestamp"]))
        return rows[-count:]
    except Exception as exc:
        logger.debug("marketstack candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
