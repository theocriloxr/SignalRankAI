from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
from typing import Any, Mapping

from sqlalchemy import text
from core.redis_state import state
from db.session import get_session
from .data_quality import normalise_candles

logger = logging.getLogger(__name__)

_MAX_QUEUE = max(100, int(os.getenv("ADAPTIVE_CANDLE_QUEUE_MAX", "2000") or 2000))
_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_MAX_QUEUE)
_LAST_SNAPSHOT: dict[tuple[str, str], tuple[int, float]] = {}
_LOCK = threading.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _capture_db_priority() -> str:
    if str(os.getenv("FULL_SYSTEM_STAGING_TEST_ACTIVE") or "").strip() == "1":
        return "interactive"
    value = str(os.getenv("ADAPTIVE_CANDLE_DB_PRIORITY") or "background").strip().lower()
    return value if value in {"interactive", "critical", "background", "analytics"} else "background"


def enqueue_market_snapshot(asset: str, market_data: Mapping[str, Any]) -> int:
    """Queue new candle suffixes without blocking strategy evaluation on PostgreSQL."""
    if not _env_bool("ADAPTIVE_CANDLE_CAPTURE_ENABLED", True):
        return 0
    queued = 0
    max_per_tf = max(10, min(500, int(os.getenv("ADAPTIVE_CANDLE_CAPTURE_MAX_PER_TIMEFRAME", "200") or 200)))
    now = time.monotonic()
    for timeframe, tf_data in market_data.items():
        if not isinstance(tf_data, Mapping) or timeframe.startswith("_"):
            continue
        rows = normalise_candles(tf_data.get("candles") or [])[-max_per_tf:]
        if not rows:
            continue
        last_ts = int(rows[-1].get("open_time_ms") or 0)
        key = (str(asset).upper(), str(timeframe).lower())
        with _LOCK:
            previous = _LAST_SNAPSHOT.get(key)
            if previous and previous[0] == last_ts and now - previous[1] < 1800:
                continue
            _LAST_SNAPSHOT[key] = (last_ts, now)
        payload = {
            "asset": key[0],
            "timeframe": key[1],
            "provider": str(tf_data.get("source") or tf_data.get("provider") or "unknown")[:64],
            "candles": rows,
        }
        try:
            _QUEUE.put_nowait(payload)
            queued += 1
        except queue.Full:
            try:
                state.set_sync("adaptive:candle_capture:backpressure", "1", ex=300)
            except Exception:
                pass
            logger.warning("[adaptive_candles] queue full; snapshot dropped asset=%s tf=%s", asset, timeframe)
            break
    return queued


def queue_depth() -> int:
    return int(_QUEUE.qsize())


def _take_batch(max_items: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while len(out) < max_items:
        try:
            out.append(_QUEUE.get_nowait())
        except queue.Empty:
            break
    return out


async def persist_queued_snapshots(max_items: int = 12) -> dict[str, int]:
    batch = _take_batch(max(1, max_items))
    if not batch:
        return {"snapshots": 0, "candles": 0}
    records: list[dict[str, Any]] = []
    for item in batch:
        candles = list(item.get("candles") or [])
        for index, candle in enumerate(candles):
            ts = int(candle.get("open_time_ms") or 0)
            if not ts:
                continue
            records.append({
                "symbol": item["asset"],
                "timeframe": item["timeframe"],
                "open_time_ms": ts,
                "close_time_ms": candle.get("close_time_ms"),
                "open": float(candle.get("open") or 0),
                "high": float(candle.get("high") or 0),
                "low": float(candle.get("low") or 0),
                "close": float(candle.get("close") or 0),
                "volume": float(candle.get("volume") or 0),
                "is_final": bool(candle.get("is_final", index < len(candles) - 1)),
            })
    if not records:
        return {"snapshots": len(batch), "candles": 0}
    inserted = 0
    try:
        async with get_session(priority=_capture_db_priority(), label="adaptive.candle_capture", timeout_seconds=float(os.getenv("ADAPTIVE_CANDLE_DB_TIMEOUT_SECONDS", "4") or 4)) as session:
            # One analytics owner plus NOT EXISTS avoids repeated inserts without adding a
            # blocking unique-index migration to a potentially large legacy candle table.
            result = await session.execute(text("""
                INSERT INTO market_candles(symbol,timeframe,open_time_ms,close_time_ms,open,high,low,close,volume,is_final,updated_at)
                SELECT :symbol,:timeframe,:open_time_ms,:close_time_ms,:open,:high,:low,:close,:volume,:is_final,NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM market_candles
                    WHERE symbol=:symbol AND timeframe=:timeframe AND open_time_ms=:open_time_ms
                )
            """), records)
            await session.commit()
            inserted = max(0, int(getattr(result, "rowcount", 0) or 0))
    except Exception:
        # Requeue a bounded suffix so transient DB pressure does not discard all evidence.
        for item in batch[-max(1, len(batch)//2):]:
            try:
                _QUEUE.put_nowait(item)
            except queue.Full:
                break
        raise
    try:
        state.set_sync("adaptive:candle_capture:last_inserted", str(inserted), ex=3600)
        state.set_sync("adaptive:candle_capture:queue_depth", str(queue_depth()), ex=3600)
    except Exception:
        pass
    return {"snapshots": len(batch), "candles": inserted}


async def candle_capture_loop(stop_event: asyncio.Event) -> None:
    interval = max(2.0, float(os.getenv("ADAPTIVE_CANDLE_CAPTURE_INTERVAL_SECONDS", "10") or 10))
    batch_size = max(1, int(os.getenv("ADAPTIVE_CANDLE_CAPTURE_BATCH_SIZE", "12") or 12))
    while not stop_event.is_set():
        try:
            result = await persist_queued_snapshots(batch_size)
            if result["snapshots"]:
                logger.info("[adaptive_candles] persisted result=%s queue_depth=%s", result, queue_depth())
        except Exception as exc:
            logger.info("[adaptive_candles] persistence deferred error=%s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
