"""Tradier market time-sales adapter for stock symbols."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _interval(value: str) -> str | None:
    return {"1m": "1min", "5m": "5min", "15m": "15min"}.get(str(value or "").lower())


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    token = str(os.getenv("TRADIER_TOKEN") or "").strip()
    interval = _interval(timeframe)
    if not token or not interval:
        return []
    count = max(2, min(1000, int(limit or 200)))
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes={"1min": 1, "5min": 5, "15min": 15}[interval] * (count + 10))
    base = str(os.getenv("TRADIER_BASE_URL") or "https://api.tradier.com/v1").rstrip("/")
    params = {
        "symbol": str(symbol).upper().strip(),
        "interval": interval,
        "start": start.strftime("%Y-%m-%d %H:%M"),
        "end": end.strftime("%Y-%m-%d %H:%M"),
        "session_filter": "all",
    }
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    client = httpx_client.get_client("tradier")
    if client is None:
        return []
    try:
        response = await client.get(f"{base}/markets/timesales", params=params, headers=headers, timeout=min(12.0, max(1.0, float(timeout))))
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        series = payload.get("series") if isinstance(payload, dict) else None
        items = series.get("data") if isinstance(series, dict) else None
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        rows: List[Dict[str, Any]] = []
        for item in items:
            try:
                rows.append(
                    {
                        "timestamp": item.get("time") or item.get("timestamp"),
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
        logger.debug("tradier candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
