"""EODHD historical/intraday OHLCV adapter.

Intraday data is classified as delayed/historical evidence unless the account
and endpoint certification prove otherwise.  The adapter never labels it as an
execution quote.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List

from services.asset_mapper import classify_asset
from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _ticker(symbol: str) -> str:
    raw = str(symbol or "").upper().strip().replace("/", "").replace("_", "").replace("-", "")
    kind = str(classify_asset(raw)).lower()
    if kind in {"fx", "forex"} or (len(raw) == 6 and raw[:3].isalpha() and raw[3:].isalpha()):
        return f"{raw}.FOREX"
    if kind == "crypto" or raw.endswith(("USDT", "USDC")) or raw.startswith(("BTC", "ETH")):
        base = raw.removesuffix("USDT").removesuffix("USDC").removesuffix("USD")
        return f"{base}-USD.CC"
    if "." in str(symbol):
        return str(symbol).upper().strip()
    return f"{raw}.US"


def _interval(timeframe: str) -> str | None:
    return {"1m": "1m", "5m": "5m", "1h": "1h"}.get(str(timeframe or "").lower())


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    token = str(os.getenv("EODHD_API_KEY") or os.getenv("EODHD_API_TOKEN") or "").strip()
    if not token:
        return []
    tf = str(timeframe or "1d").strip().lower()
    count = max(2, min(1000, int(limit or 200)))
    params: dict[str, Any] = {"api_token": token, "fmt": "json"}
    if tf == "1d":
        endpoint = f"https://eodhd.com/api/eod/{_ticker(symbol)}"
        params.update({"period": "d", "order": "d"})
    else:
        interval = _interval(tf)
        if not interval:
            return []
        endpoint = f"https://eodhd.com/api/intraday/{_ticker(symbol)}"
        now = datetime.now(timezone.utc)
        seconds = {"1m": 60, "5m": 300, "1h": 3600}[tf]
        params.update(
            {
                "interval": interval,
                "from": int((now - timedelta(seconds=seconds * (count + 10))).timestamp()),
                "to": int(now.timestamp()),
            }
        )
    client = httpx_client.get_client("eodhd")
    if client is None:
        return []
    request_timeout = min(12.0, max(1.0, float(timeout)))
    try:
        response = await client.get(endpoint, params=params, timeout=request_timeout)
        if response.status_code != 200:
            return []
        payload = response.json() or []
        if not isinstance(payload, list):
            return []
        rows: List[Dict[str, Any]] = []
        for item in payload[:count]:
            if not isinstance(item, dict):
                continue
            try:
                rows.append(
                    {
                        "timestamp": item.get("timestamp") or item.get("date") or item.get("datetime"),
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": float(item.get("volume") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        rows.reverse() if tf == "1d" else None
        rows.sort(key=lambda row: str(row["timestamp"]))
        return rows[-count:]
    except Exception as exc:
        logger.debug("eodhd candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
