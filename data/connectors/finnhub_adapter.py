"""Finnhub candle adapter for stock, forex and crypto endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List

from services.asset_mapper import classify_asset
from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _resolution(timeframe: str) -> str | None:
    return {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D"}.get(str(timeframe or "").lower())


def _route_symbol(symbol: str) -> tuple[str, str]:
    raw = str(symbol or "").upper().strip()
    if ":" in raw:
        prefix = raw.split(":", 1)[0]
        if prefix in {"OANDA", "FXCM", "IC MARKETS"}:
            return "forex", raw
        if prefix in {"BINANCE", "COINBASE", "KRAKEN"}:
            return "crypto", raw
    kind = str(classify_asset(raw)).lower()
    if kind in {"fx", "forex"}:
        pair = raw.replace("/", "_").replace("-", "_")
        if "_" not in pair and len(pair) == 6:
            pair = f"{pair[:3]}_{pair[3:]}"
        return "forex", f"OANDA:{pair}"
    if kind == "crypto" or raw.endswith(("USDT", "USDC")):
        return "crypto", f"BINANCE:{raw.replace('/', '').replace('-', '')}"
    return "stock", raw


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    token = str(os.getenv("FINNHUB_API_KEY") or "").strip()
    resolution = _resolution(timeframe)
    if not token or not resolution:
        return []
    kind, provider_symbol = _route_symbol(symbol)
    count = max(2, min(1000, int(limit or 200)))
    seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}.get(str(timeframe).lower(), 3600)
    now = datetime.now(timezone.utc)
    endpoint = {
        "stock": "https://finnhub.io/api/v1/stock/candle",
        "forex": "https://finnhub.io/api/v1/forex/candle",
        "crypto": "https://finnhub.io/api/v1/crypto/candle",
    }[kind]
    params = {
        "symbol": provider_symbol,
        "resolution": resolution,
        "from": int((now - timedelta(seconds=seconds * (count + 10))).timestamp()),
        "to": int(now.timestamp()),
        "token": token,
    }
    client = httpx_client.get_client("finnhub")
    if client is None:
        return []
    try:
        response = await client.get(endpoint, params=params, timeout=min(12.0, max(1.0, float(timeout))))
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        if not isinstance(payload, dict) or str(payload.get("s") or "").lower() != "ok":
            return []
        arrays = [list(payload.get(key) or []) for key in ("t", "o", "h", "l", "c")]
        volumes = list(payload.get("v") or [])
        length = min(map(len, arrays)) if arrays else 0
        rows: List[Dict[str, Any]] = []
        for index in range(max(0, length - count), length):
            try:
                rows.append(
                    {
                        "timestamp": int(arrays[0][index]) * 1000,
                        "open": float(arrays[1][index]),
                        "high": float(arrays[2][index]),
                        "low": float(arrays[3][index]),
                        "close": float(arrays[4][index]),
                        "volume": float(volumes[index] if index < len(volumes) else 0.0),
                    }
                )
            except (TypeError, ValueError):
                continue
        return rows
    except Exception as exc:
        logger.debug("finnhub candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
