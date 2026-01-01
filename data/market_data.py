from __future__ import annotations

import asyncio
import os
from typing import Iterable

from data.fetcher import fetch_market_data as fetch_market_data_rest
from db.market_cache import get_recent_candles
from db.session import ENGINE, get_session


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


async def fetch_market_data_cached(asset: str, timeframes: Iterable[str]) -> dict:
    """Fetch market data from Postgres cache first, then fallback to REST.

    The WS ingestor continuously upserts candles into Postgres. This reader
    allows the engine to consume the stream-derived cache.

    If the cache is missing/insufficient, we fallback to existing REST fetching
    so production keeps working even when WS is unavailable.
    """

    tfs = [str(tf).strip() for tf in (timeframes or []) if str(tf).strip()]
    if not tfs:
        return {}

    want = _env_int("MARKET_CACHE_MIN_CANDLES", 80)
    limit = _env_int("MARKET_CACHE_READ_LIMIT", 200)
    use_cache = _env_bool("MARKET_CACHE_ENABLED", True)

    out: dict = {}

    if use_cache and ENGINE is not None:
        try:
            async with get_session() as session:
                for tf in tfs:
                    candles = await get_recent_candles(session, symbol=asset, timeframe=tf, limit=limit)
                    if candles and len(candles) >= want:
                        out[tf] = {"candles": candles}
                await session.commit()
        except Exception:
            out = out or {}

    # Backfill missing timeframes via REST fetcher (and indicators calculation).
    missing = [tf for tf in tfs if tf not in out]
    if missing:
        rest_timeout = float(_env_int("MARKET_REST_TIMEOUT_SECONDS", 25))
        try:
            rest = await asyncio.wait_for(
                asyncio.to_thread(fetch_market_data_rest, asset, missing),
                timeout=max(1.0, rest_timeout),
            )
        except asyncio.TimeoutError:
            rest = {}
        for tf, payload in (rest or {}).items():
            out[tf] = payload

    # If cache returned candles without indicators, compute them using existing fetcher pipeline:
    # easiest: re-run calculate_indicators for cached candles.
    try:
        from data.indicators import calculate_indicators

        for tf in list(out.keys()):
            payload = out.get(tf) or {}
            if "indicators" not in payload:
                candles = payload.get("candles") or []
                if candles:
                    payload["indicators"] = calculate_indicators(candles)
                    out[tf] = payload
    except Exception:
        pass

    return out
