"""Alpaca Market Data historical bars adapter (stocks and crypto)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List

from services.asset_mapper import classify_asset
from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _timeframe(value: str) -> str | None:
    return {"1m": "1Min", "5m": "5Min", "15m": "15Min", "1h": "1Hour", "4h": "4Hour", "1d": "1Day"}.get(str(value or "").lower())


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    key = str(os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or "").strip()
    secret = str(os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or "").strip()
    tf = _timeframe(timeframe)
    if not key or not secret or not tf:
        return []
    raw = str(symbol or "").upper().strip()
    kind = str(classify_asset(raw)).lower()
    is_crypto = kind == "crypto" or raw.endswith(("USDT", "USDC")) or "/" in raw
    count = max(2, min(1000, int(limit or 200)))
    end = datetime.now(timezone.utc)
    seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(str(timeframe).lower(), 3600)
    start = end - timedelta(seconds=seconds * (count + 20))
    if is_crypto:
        canonical = raw.replace("-", "/").replace("_", "/")
        if "/" not in canonical:
            for quote in ("USDT", "USDC", "USD"):
                if canonical.endswith(quote):
                    canonical = f"{canonical[:-len(quote)]}/USD"
                    break
        endpoint = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
        params = {"symbols": canonical, "timeframe": tf, "start": start.isoformat(), "end": end.isoformat(), "limit": count, "sort": "asc"}
    else:
        canonical = raw
        endpoint = f"https://data.alpaca.markets/v2/stocks/{canonical}/bars"
        params = {"timeframe": tf, "start": start.isoformat(), "end": end.isoformat(), "limit": count, "sort": "asc", "adjustment": "raw"}
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    client = httpx_client.get_client("alpaca")
    if client is None:
        return []
    try:
        response = await client.get(endpoint, params=params, headers=headers, timeout=min(12.0, max(1.0, float(timeout))))
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        bars = payload.get("bars") if isinstance(payload, dict) else None
        if isinstance(bars, dict):
            bars = bars.get(canonical) or bars.get(raw) or next(iter(bars.values()), [])
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
        return rows[-count:]
    except Exception as exc:
        logger.debug("alpaca candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
