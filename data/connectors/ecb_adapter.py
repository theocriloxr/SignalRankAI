"""ECB reference-rate adapter for daily FX learning/context.

The ECB publishes official daily reference rates without an API key.  These
values are daily reference observations, not intraday executable quotes, so
this adapter intentionally returns data only for the 1d timeframe and must not
satisfy day-profile 5m/15m/1h delivery requirements.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)
try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"

def _split_pair(symbol: str) -> tuple[str, str] | None:
    text = str(symbol or "").upper().replace("/", "").replace("_", "").replace("-", "")
    if len(text) != 6 or not text.isalpha():
        return None
    return text[:3], text[3:]

async def _series(currency: str, *, days: int, timeout: float) -> dict[str, float]:
    if currency == "EUR":
        return {}
    start = (date.today() - timedelta(days=max(30, days * 2))).isoformat()
    url = f"{_BASE}/D.{currency}.EUR.SP00.A"
    params = {"startPeriod": start, "format": "csvdata"}
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "SignalRankAI/1.0"}) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
    rows = csv.DictReader(io.StringIO(response.text))
    out: dict[str, float] = {}
    for row in rows:
        period = row.get("TIME_PERIOD")
        value = row.get("OBS_VALUE")
        try:
            if period and value:
                out[str(period)] = float(value)
        except Exception:
            continue
    return out

async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 8.0) -> list[dict[str, Any]]:
    if httpx is None or str(timeframe).lower() not in {"1d", "d", "day", "daily"}:
        return []
    pair = _split_pair(symbol)
    if not pair:
        return []
    base, quote = pair
    try:
        base_rates, quote_rates = await asyncio.gather(
            _series(base, days=limit, timeout=timeout) if base != "EUR" else asyncio.sleep(0, result={}),
            _series(quote, days=limit, timeout=timeout) if quote != "EUR" else asyncio.sleep(0, result={}),
        )
        dates = sorted((set(base_rates) if base != "EUR" else set(quote_rates)) & (set(quote_rates) if quote != "EUR" else set(base_rates)))
        if base == "EUR":
            dates = sorted(quote_rates)
        elif quote == "EUR":
            dates = sorted(base_rates)
        out=[]
        for day in dates[-max(1, int(limit)):]:
            base_per_eur = 1.0 if base == "EUR" else float(base_rates[day])
            quote_per_eur = 1.0 if quote == "EUR" else float(quote_rates[day])
            px = quote_per_eur / base_per_eur
            ts = int(__import__("datetime").datetime.fromisoformat(day).timestamp())
            out.append({"timestamp": ts, "open": px, "high": px, "low": px, "close": px, "volume": 0.0, "analysis_only": True, "source": "ecb_reference_rate"})
        return out
    except Exception as exc:
        logger.debug("ecb_adapter failed symbol=%s err=%s", symbol, exc)
        return []

def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 8.0):
    from utils.async_runner import run_sync
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
