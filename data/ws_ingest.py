from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass
from typing import Optional

from data.binance_ws import iter_events as binance_iter_events
from data.cryptocompare_ws import iter_events as cryptocompare_iter_events
from db.market_cache import prune_old_candles, upsert_market_candle, upsert_market_tick
from db.session import get_session, is_db_configured
from data.pair_discovery import get_all_trending_pairs
from data.fetcher import is_crypto
from core.redis_state import state
import logging
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def _crypto_timeframes() -> list[str]:
    raw = (os.getenv("CRYPTO_TIMEFRAMES") or "1m,5m,15m,1h,4h,1d").strip()
    tfs = [x.strip().lower() for x in raw.split(",") if x.strip()]
    # Keep only intervals we can build/consume.
    allow = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}
    return [t for t in tfs if t in allow]


def _crypto_symbols() -> list[str]:
    raw = (os.getenv("CRYPTO_WS_SYMBOLS") or "").strip()
    if raw:
        syms = [x.strip().upper() for x in raw.split(",") if x.strip()]
    else:
        try:
            syms = [s for s in (get_all_trending_pairs() or []) if is_crypto(s)]
        except Exception:
            syms = []
    max_syms = _env_int("CRYPTO_WS_MAX_SYMBOLS", 20)
    return (syms or [])[: max(1, int(max_syms))]


def _tf_seconds(tf: str) -> int:
    tf = (tf or "").strip().lower()
    mapping = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "8h": 28800,
        "12h": 43200,
        "1d": 86400,
    }
    return int(mapping.get(tf) or 0)


@dataclass
class _CandleState:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class _CryptoCompareCandleBuilder:
    def __init__(self, *, intervals: list[str]) -> None:
        self._intervals = list(intervals)
        # key: (symbol, timeframe)
        self._cur: dict[tuple[str, str], _CandleState] = {}

    def update(self, *, symbol: str, price: float, volume: float, event_time_ms: int) -> list[dict]:
        out: list[dict] = []
        sym = str(symbol or "").upper().strip()
        if not sym:
            return out
        ts_ms = int(event_time_ms)

        for tf in self._intervals:
            sec = _tf_seconds(tf)
            if sec <= 0:
                continue
            bucket_ms = sec * 1000
            open_time_ms = (ts_ms // bucket_ms) * bucket_ms
            close_time_ms = open_time_ms + bucket_ms
            key = (sym, tf)
            cur = self._cur.get(key)

            if cur is None or int(cur.open_time_ms) != int(open_time_ms):
                # Finalize previous candle as final if we have one.
                if cur is not None:
                    out.append(
                        {
                            "type": "kline",
                            "symbol": sym,
                            "timeframe": tf,
                            "open_time_ms": int(cur.open_time_ms),
                            "close_time_ms": int(cur.close_time_ms),
                            "open": float(cur.open),
                            "high": float(cur.high),
                            "low": float(cur.low),
                            "close": float(cur.close),
                            "volume": float(cur.volume),
                            "is_final": True,
                        }
                    )

                cur = _CandleState(
                    open_time_ms=int(open_time_ms),
                    close_time_ms=int(close_time_ms),
                    open=float(price),
                    high=float(price),
                    low=float(price),
                    close=float(price),
                    volume=float(volume or 0.0),
                )
                self._cur[key] = cur
            else:
                cur.high = max(float(cur.high), float(price))
                cur.low = min(float(cur.low), float(price))
                cur.close = float(price)
                cur.volume = float(cur.volume) + float(volume or 0.0)
                self._cur[key] = cur

            # Emit current candle as non-final (upsert keeps it fresh).
            out.append(
                {
                    "type": "kline",
                    "symbol": sym,
                    "timeframe": tf,
                    "open_time_ms": int(cur.open_time_ms),
                    "close_time_ms": int(cur.close_time_ms),
                    "open": float(cur.open),
                    "high": float(cur.high),
                    "low": float(cur.low),
                    "close": float(cur.close),
                    "volume": float(cur.volume),
                    "is_final": False,
                }
            )

        return out


def _choose_ws_provider() -> str:
    # Explicit override
    forced = (os.getenv("CRYPTO_WS_PROVIDER") or "").strip().lower()
    if forced in {"binance", "cryptocompare"}:
        return forced

    # Auto: prefer the configured data provider, but we will fall back.
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
    if provider in {"binance", "cryptocompare"}:
        return provider
    return "binance"


async def run_ws_ingestor(stop_event: Optional[asyncio.Event] = None) -> None:
    """Consume WS (Binance or CryptoCompare) and persist market data into Postgres.

    Auto-fallback:
    - If Binance WS is unreachable/geo-blocked, we can fall back to CryptoCompare WS.
    - If CryptoCompare WS is rate-limited/unavailable, we can fall back to Binance WS.

    Non-fatal by design:
    - If DATABASE_URL is missing or both providers fail, this should not crash the process.
    """

    if not _env_bool("CRYPTO_WS_ENABLED", False):
        return

    if not is_db_configured():
        return

    symbols = _crypto_symbols()
    intervals = _crypto_timeframes()
    if not symbols or not intervals:
        return

    keep_last = _env_int("MARKET_CANDLE_KEEP_LAST", 500)
    prune_every = _env_int("MARKET_CANDLE_PRUNE_EVERY", 200)

    flush_every = _env_int("WS_DB_FLUSH_EVERY", 25)
    stale_seconds = float(_env_int("WS_STALE_SECONDS", 45))

    # CryptoCompare does not provide klines; we build candles from trades/ticks.
    cc_builder = _CryptoCompareCandleBuilder(intervals=intervals)

    async def _consume_provider(provider: str) -> bool:
        """Return True if running, False if stalled (no events)."""

        logger.info(f"[ws_ingest] provider_start={provider} symbols={len(symbols)} intervals={len(intervals)}")

        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=max(100, flush_every * 10))
        stop = asyncio.Event()

        async def _feeder() -> None:
            try:
                if provider == "binance":
                    async for ev in binance_iter_events(symbols=symbols, intervals=intervals):
                        if stop.is_set():
                            return
                        await q.put(ev)
                else:
                    async for ev in cryptocompare_iter_events(symbols=symbols):
                        if stop.is_set():
                            return
                        await q.put(ev)
            except Exception:
                # allow caller to switch provider
                return

        feeder_task = asyncio.create_task(_feeder())
        buffered = 0

        # Batch buffers
        tick_buf: dict[str, dict] = {}
        candle_buf: list[dict] = []

        async def _flush() -> None:
            nonlocal tick_buf, candle_buf
            if not tick_buf and not candle_buf:
                return
            try:
                async with get_session() as session:
                    for t in tick_buf.values():
                        await upsert_market_tick(
                            session,
                            symbol=str(t.get("symbol") or ""),
                            price=float(t.get("price") or 0.0),
                            event_time_ms=t.get("event_time_ms"),
                        )
                    for c in candle_buf:
                        await upsert_market_candle(
                            session,
                            symbol=str(c.get("symbol") or ""),
                            timeframe=str(c.get("timeframe") or ""),
                            open_time_ms=int(c.get("open_time_ms") or 0),
                            close_time_ms=c.get("close_time_ms"),
                            open=float(c.get("open") or 0.0),
                            high=float(c.get("high") or 0.0),
                            low=float(c.get("low") or 0.0),
                            close=float(c.get("close") or 0.0),
                            volume=float(c.get("volume") or 0.0),
                            is_final=bool(c.get("is_final")),
                        )
                    await session.commit()
            except Exception:
                # Best-effort: drop this batch
                pass
            tick_buf = {}
            candle_buf = []

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    stop.set()
                    feeder_task.cancel()
                    await _flush()
                    return True

                # If no events arrive for a while, switch provider.
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=max(5.0, stale_seconds))
                except asyncio.TimeoutError:
                    # stall
                    logger.warning(f"[ws_ingest] provider_stalled={provider} stale_seconds={stale_seconds}")
                    stop.set()
                    feeder_task.cancel()
                    await _flush()
                    return False

                # Normalize and buffer
                et_ms = ev.get("event_time_ms")
                if ev.get("type") == "tick":
                    sym = str(ev.get("symbol") or "").upper().strip()
                    tick = {
                        "symbol": str(ev.get("symbol") or "").upper().strip(),
                        "price": float(ev.get("price") or 0.0),
                        "event_time_ms": et_ms,
                    }
                    tick_buf[sym] = tick
                    try:
                        state.set_latest_tick_sync(sym, float(tick["price"]), event_time_ms=et_ms, source=provider)
                    except Exception:
                        pass
                elif ev.get("type") == "kline":
                    candle_buf.append(ev)
                elif provider == "cryptocompare" and ev.get("type") in {"trade", "tick"}:
                    # Build candles from trades/ticks.
                    sym = str(ev.get("symbol") or "").upper().strip()
                    price = float(ev.get("price") or 0.0)
                    vol = float(ev.get("volume") or 0.0) if ev.get("type") == "trade" else 0.0
                    now_ms = int(time.time() * 1000)
                    ts_ms = int(et_ms or now_ms)
                    try:
                        state.set_latest_tick_sync(sym, price, event_time_ms=ts_ms, source=provider)
                    except Exception:
                        pass
                    for c in cc_builder.update(symbol=sym, price=price, volume=vol, event_time_ms=ts_ms):
                        candle_buf.append(c)

                buffered += 1
                if buffered >= flush_every:
                    buffered = 0
                    await _flush()

                    # Periodic prune (lightweight)
                    if prune_every > 0:
                        try:
                            async with get_session() as session:
                                for sym in symbols:
                                    for tf in intervals:
                                        await prune_old_candles(session, symbol=sym, timeframe=tf, keep_last=keep_last)
                                await session.commit()
                        except Exception:
                            pass
        finally:
            stop.set()
            feeder_task.cancel()
            with contextlib.suppress(Exception):
                await feeder_task

    # Main loop: try preferred provider, then fallback, and keep retrying.
    preferred = _choose_ws_provider()
    providers = [preferred, "cryptocompare" if preferred == "binance" else "binance"]

    while stop_event is None or not stop_event.is_set():
        for p in providers:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                logger.info(f"[ws_ingest] provider_try={p}")
                ok = await _consume_provider(p)
            except Exception:
                ok = False
            if ok:
                # Normal shutdown requested.
                return
            # If stalled, try the other provider.
            logger.info(f"[ws_ingest] provider_switch_from={p}")
        await asyncio.sleep(2.0)
