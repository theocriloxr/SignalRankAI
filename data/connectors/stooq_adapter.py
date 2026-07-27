"""Stooq public daily CSV historical adapter.

Stooq is historical/best-effort only and must not be used as execution truth.
"""
from __future__ import annotations

import csv
from io import StringIO
import logging
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _symbol(value: str) -> str:
    raw = str(value or "").lower().strip()
    if "." in raw:
        return raw
    if raw.startswith("^"):
        return raw[1:]
    if len(raw) == 6 and raw.isalpha():
        return raw
    return f"{raw}.us"


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    if str(timeframe or "").lower() not in {"1d", "d", "day", "daily"}:
        return []
    client = httpx_client.get_client("stooq")
    if client is None:
        return []
    try:
        response = await client.get(
            "https://stooq.com/q/d/l/",
            params={"s": _symbol(symbol), "i": "d"},
            timeout=min(12.0, max(1.0, float(timeout))),
        )
        if response.status_code != 200:
            return []
        text = str(getattr(response, "text", "") or "")
        rows: List[Dict[str, Any]] = []
        for item in csv.DictReader(StringIO(text)):
            try:
                rows.append(
                    {
                        "timestamp": item.get("Date"),
                        "open": float(item["Open"]),
                        "high": float(item["High"]),
                        "low": float(item["Low"]),
                        "close": float(item["Close"]),
                        "volume": float(item.get("Volume") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rows[-max(2, int(limit or 200)):]
    except Exception as exc:
        logger.debug("stooq candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
