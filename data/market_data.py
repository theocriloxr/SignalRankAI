from __future__ import annotations

import asyncio
import os
from typing import Iterable

from data.fetcher import fetch_market_data as fetch_market_data_rest
from db.market_cache import get_recent_candles
from db.session import get_session


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
        # Fallback providers (CryptoCompare/Bybit) can be slower when Binance is blocked; allow longer by default.
        rest_timeout = float(_env_int("MARKET_REST_TIMEOUT_SECONDS", 60))
        try:
            rest = await asyncio.wait_for(
                asyncio.to_thread(fetch_market_data_rest, asset, missing),
                timeout=max(1.0, rest_timeout),
            )
        except asyncio.TimeoutError:
            rest = {}
        for tf, payload in (rest or {}).items():
            out[tf] = payload

        # Best-effort write-through into Postgres cache tables.
        if ENGINE is not None and _env_bool("MARKET_CACHE_WRITE_THROUGH", True):
            try:
                from datetime import datetime
                from db.market_cache import upsert_market_candle, upsert_market_tick

                def _ts_to_ms(v):
                    if v is None:
                        return None
                    if isinstance(v, (int, float)):
                        # Heuristic: < 10^12 likely seconds.
                        n = int(v)
                        return n * 1000 if n < 1_000_000_000_000 else n
                    s = str(v).strip()
                    if not s:
                        return None
                    try:
                        # AlphaVantage returns ISO without timezone; treat as UTC.
                        dt = datetime.fromisoformat(s.replace("Z", ""))
                        return int(dt.timestamp() * 1000)
                    except Exception:
                        return None

                async with get_session() as session:
                    last_tick_ms = None
                    last_tick_price = None
                    for tf, payload in (rest or {}).items():
                        candles = (payload or {}).get("candles") or []
                        for c in candles:
                            try:
                                ts_ms = _ts_to_ms(c.get("timestamp"))
                                if ts_ms is None:
                                    continue
                                await upsert_market_candle(
                                    session,
                                    symbol=str(asset),
                                    timeframe=str(tf),
                                    open_time_ms=int(ts_ms),
                                    open=float(c.get("open")),
                                    high=float(c.get("high")),
                                    low=float(c.get("low")),
                                    close=float(c.get("close")),
                                    volume=float(c.get("volume") or 0.0),
                                    is_final=True,
                                )
                                last_tick_ms = int(ts_ms)
                                last_tick_price = float(c.get("close"))
                            except Exception:
                                continue
                    if last_tick_price is not None:
                        try:
                            await upsert_market_tick(
                                session,
                                symbol=str(asset),
                                price=float(last_tick_price),
                                event_time_ms=int(last_tick_ms) if last_tick_ms is not None else None,
                            )
                        except Exception:
                            pass
                    await session.commit()
            except Exception:
                pass

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
