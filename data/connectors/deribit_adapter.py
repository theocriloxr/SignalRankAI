"""Deribit public TradingView-chart candle adapter.

Official endpoint: ``public/get_tradingview_chart_data``.  This adapter is
read-only and requires no credential.  Instrument names must be canonical
Deribit instruments, for example ``BTC-PERPETUAL`` or an option contract.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _instrument(symbol: str) -> str:
    raw = str(symbol or "").upper().strip().replace("/", "-").replace("_", "-")
    if raw in {"BTCUSD", "BTC-USDT", "BTCUSDT", "BTC-USD"}:
        return "BTC-PERPETUAL"
    if raw in {"ETHUSD", "ETH-USDT", "ETHUSDT", "ETH-USD"}:
        return "ETH-PERPETUAL"
    return raw


def _resolution(timeframe: str) -> str | None:
    return {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "4h": "240",
        "1d": "1D",
    }.get(str(timeframe or "").strip().lower())


def _period_ms(timeframe: str) -> int:
    return {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }.get(str(timeframe or "").strip().lower(), 3_600_000)


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    resolution = _resolution(timeframe)
    if not resolution:
        return []
    count = max(2, min(1000, int(limit or 200)))
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - _period_ms(timeframe) * (count + 2)
    client = httpx_client.get_client("deribit")
    if client is None:
        return []
    params = {
        "instrument_name": _instrument(symbol),
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
        "resolution": resolution,
    }
    request_timeout = min(12.0, max(1.0, float(timeout)))

    async def _do():
        response = await client.get(
            "https://www.deribit.com/api/v2/public/get_tradingview_chart_data",
            params=params,
            timeout=request_timeout,
        )
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or str(result.get("status") or "").lower() not in {"ok", "no_data"}:
            return []
        ticks = list(result.get("ticks") or [])
        opens = list(result.get("open") or [])
        highs = list(result.get("high") or [])
        lows = list(result.get("low") or [])
        closes = list(result.get("close") or [])
        volumes = list(result.get("volume") or [])
        length = min(len(ticks), len(opens), len(highs), len(lows), len(closes))
        rows: List[Dict[str, Any]] = []
        for index in range(max(0, length - count), length):
            try:
                rows.append(
                    {
                        "timestamp": int(ticks[index]),
                        "open": float(opens[index]),
                        "high": float(highs[index]),
                        "low": float(lows[index]),
                        "close": float(closes[index]),
                        "volume": float(volumes[index] if index < len(volumes) else 0.0),
                    }
                )
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda row: int(row["timestamp"]))
        return rows

    try:
        return await asyncio.wait_for(httpx_client.retry_async(_do, retries=2, backoff=0.35), timeout=request_timeout + 1)
    except Exception as exc:
        logger.debug("deribit candle request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
