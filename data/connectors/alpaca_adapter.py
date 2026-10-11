"""Alpaca Market Data historical bars adapter (stocks and crypto)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
import re
from typing import Any, Dict, List

from services.asset_mapper import classify_asset
from data.connectors.sdk_adapters import crypto_pair
from data.sdk_gateway import read_sdk
from market_data_sdk.worker import INTERVALS, normalize_bars
from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _timeframe(value: str) -> str | None:
    return {"1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min", "1h": "1Hour", "4h": "4Hour", "1d": "1Day"}.get(
        str(value or "").lower()
    )


async def _async_get_candles(
    symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0
) -> List[Dict[str, Any]]:
    key = str(os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or "").strip()
    secret = str(os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or "").strip()
    tf = _timeframe(timeframe)
    if not key or not secret or not tf:
        return []
    raw = str(symbol or "").upper().strip()
    kind = str(classify_asset(raw)).lower()
    is_crypto = kind == "crypto"
    if type(limit) is not int or not 1 <= limit <= 1000:
        return []
    count = limit
    canonical = crypto_pair(raw) if is_crypto else raw
    if not canonical or (not is_crypto and not re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}", canonical)):
        return []
    if kind in {"fx", "forex", "commodity", "index"}:
        return []
    feed = os.getenv("ALPACA_DATA_FEED", "iex").strip().lower()
    if feed not in {"iex", "sip", "delayed_sip"}:
        return []
    transport = os.getenv("ALPACA_DATA_TRANSPORT", "rest").strip().lower()
    if transport == "sdk":
        rows = await asyncio.to_thread(read_sdk, "alpaca_bars", dict(symbol=canonical,
                                       timeframe=timeframe, limit=count, crypto=is_crypto, feed=feed), timeout=timeout)
        return rows if isinstance(rows, list) else []
    if transport != "rest":
        return []
    end = datetime.now(timezone.utc)
    seconds = INTERVALS[str(timeframe).lower()]
    start = end - timedelta(seconds=seconds * (count + 20) * 7)
    if is_crypto:
        endpoint = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
        params = {
            "symbols": canonical,
            "timeframe": tf,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": count,
            "sort": "desc",
        }
    else:
        canonical = raw
        endpoint = f"https://data.alpaca.markets/v2/stocks/{canonical}/bars"
        params = {
            "timeframe": tf,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": count,
            "sort": "desc",
            "adjustment": "raw",
            "feed": feed,
        }
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    client = httpx_client.get_client("alpaca")
    if client is None:
        return []
    try:
        response = await client.get(
            endpoint, params=params, headers=headers, timeout=min(12.0, max(1.0, float(timeout)))
        )
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        bars = payload.get("bars") if isinstance(payload, dict) else None
        if isinstance(bars, dict):
            bars = bars.get(canonical)
        if payload.get("symbol", canonical) != canonical:
            return []
        if not isinstance(bars, list):
            return []
        rows: List[Dict[str, Any]] = []
        for item in bars:
            try:
                rows.append(
                    {
                        "timestamp": item.get("t"),
                        "open": float(item["o"]),
                        "high": float(item["h"]),
                        "low": float(item["l"]),
                        "close": float(item["c"]),
                        "volume": float(item.get("v") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return normalize_bars(rows, count)
    except Exception as exc:
        logger.debug("alpaca candle request failed: %s", type(exc).__name__)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
