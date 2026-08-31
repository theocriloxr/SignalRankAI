from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
from typing import Any, Mapping

from sqlalchemy.dialects.postgresql import insert as pg_insert
from core.redis_state import state
from db.models import MarketCandle
from db.session import get_session
from .data_quality import normalise_candles

logger = logging.getLogger(__name__)

_MAX_QUEUE = max(100, int(os.getenv("ADAPTIVE_CANDLE_QUEUE_MAX", "2000") or 2000))
_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_MAX_QUEUE)
_LAST_SNAPSHOT: dict[tuple[str, str], tuple[int, float]] = {}
_LOCK = threading.Lock()
_LOCAL_DRAIN_LOCK = threading.Lock()
_LOCAL_DRAIN_TASK: asyncio.Task | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _capture_db_priority() -> str:
    if str(os.getenv("FULL_SYSTEM_STAGING_TEST_ACTIVE") or "").strip() == "1":
        return "interactive"
    value = str(os.getenv("ADAPTIVE_CANDLE_DB_PRIORITY") or "background").strip().lower()
    return value if value in {"interactive", "critical", "background", "analytics"} else "background"


def _local_drain_batch_size() -> int:
    return max(
        1,
        int(
            os.getenv(
                "ADAPTIVE_CANDLE_LOCAL_DRAIN_BATCH_SIZE",
                os.getenv("ADAPTIVE_CANDLE_CAPTURE_BATCH_SIZE", "24") or "24",
            )
            or 24
        ),
    )


async def _drain_local_queue() -> None:
    """Drain the process-local queue in the process that produced it.

    SignalRank runs the scanner/engine and background worker as separate Railway
    processes. A Python ``queue.Queue`` is not shared between those processes,
    so relying only on the worker's ``candle_capture_loop`` leaves snapshots
    produced by the engine stranded until its local queue fills. This short-lived
    consumer is scheduled on the producer's running event loop and exits once the
    queue is empty. The worker loop remains useful for monolithic deployments.
    """
    retry_delay = max(
        0.25,
        float(os.getenv("ADAPTIVE_CANDLE_LOCAL_DRAIN_RETRY_SECONDS", "2") or 2),
    )
    while True:
        if queue_depth() <= 0:
            return
        try:
            result = await persist_queued_snapshots(_local_drain_batch_size())
            if result["snapshots"]:
                logger.info(
                    "[adaptive_candles] local_drain persisted=%s queue_depth=%s",
                    result,
                    queue_depth(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Keep the evidence queued and retry in the same producer process.
            logger.info(
                "[adaptive_candles] local_drain deferred error=%s queue_depth=%s",
                exc,
                queue_depth(),
            )
            await asyncio.sleep(retry_delay)
        else:
            # Yield to the engine between DB batches so candle persistence cannot
            # monopolise the scanner event loop during the initial history backfill.
            await asyncio.sleep(0)


def _local_drain_finished(task: asyncio.Task) -> None:
    global _LOCAL_DRAIN_TASK
    try:
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                logger.warning("[adaptive_candles] local drain task crashed: %s", exc)
    except Exception as exc:
        logger.debug("[adaptive_candles] local drain completion inspection failed: %s", exc)
    finally:
        with _LOCAL_DRAIN_LOCK:
            if _LOCAL_DRAIN_TASK is task:
                _LOCAL_DRAIN_TASK = None


def ensure_local_drain() -> bool:
    """Start one producer-local drain task when an asyncio loop is available."""
    global _LOCAL_DRAIN_TASK
    if not _env_bool("ADAPTIVE_CANDLE_LOCAL_DRAIN_ENABLED", True):
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Synchronous tests/maintenance scripts can still call
        # ``persist_queued_snapshots`` or run ``candle_capture_loop`` explicitly.
        return False

    with _LOCAL_DRAIN_LOCK:
        if _LOCAL_DRAIN_TASK is not None and not _LOCAL_DRAIN_TASK.done():
            return False
        task = loop.create_task(_drain_local_queue(), name="adaptive-candle-local-drain")
        task.add_done_callback(_local_drain_finished)
        _LOCAL_DRAIN_TASK = task
        return True


def enqueue_market_snapshot(asset: str, market_data: Mapping[str, Any]) -> int:
    """Queue only the changed candle suffix without blocking strategy evaluation.

    The former implementation re-enqueued as many as 200 historical candles
    whenever a new bar appeared. Across several assets and timeframes that
    created avoidable write pressure and made a second database look necessary.
    The first observation still backfills the bounded history; later snapshots
    contain only the previous bar (for finalisation) and the new/open bar.

    In decomposed deployments the queue is process-local, so the producer also
    schedules a local asynchronous drain. This prevents the engine service from
    depending on a different Railway process to consume Python memory it cannot
    access.
    """
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
            rows_to_queue = rows
            if previous:
                previous_ts, previous_queued_at = previous
                if last_ts == previous_ts:
                    refresh_interval = max(
                        5.0,
                        float(
                            os.getenv(
                                "ADAPTIVE_CANDLE_OPEN_UPDATE_INTERVAL_SECONDS",
                                "30",
                            )
                            or 30
                        ),
                    )
                    if now - previous_queued_at < refresh_interval:
                        continue
                    rows_to_queue = rows[-1:]
                elif last_ts > previous_ts:
                    # Include the previous open time so the now-final candle is
                    # updated, then include the newly opened bar.
                    rows_to_queue = [
                        row
                        for row in rows
                        if int(row.get("open_time_ms") or 0) >= previous_ts
                    ]
                    if not rows_to_queue:
                        rows_to_queue = rows[-2:]
            _LAST_SNAPSHOT[key] = (last_ts, now)
        payload = {
            "asset": key[0],
            "timeframe": key[1],
            "provider": str(tf_data.get("source") or tf_data.get("provider") or "unknown")[:64],
            "candles": rows_to_queue,
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

    if queued:
        ensure_local_drain()
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
        async with get_session(
            priority=_capture_db_priority(),
            label="adaptive.candle_capture",
            timeout_seconds=float(os.getenv("ADAPTIVE_CANDLE_DB_TIMEOUT_SECONDS", "20") or 20),
            drop_if_busy=False,
        ) as session:
            # The schema already has uq_market_candles_symbol_tf_open. A true
            # PostgreSQL bulk upsert both removes asyncpg bind ambiguity and
            # updates the still-open candle instead of preserving its first tick.
            chunk_size = max(
                25,
                min(
                    500,
                    int(os.getenv("ADAPTIVE_CANDLE_UPSERT_CHUNK_SIZE", "200") or 200),
                ),
            )
            for offset in range(0, len(records), chunk_size):
                chunk = records[offset : offset + chunk_size]
                stmt = pg_insert(MarketCandle).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_market_candles_symbol_tf_open",
                    set_={
                        "close_time_ms": stmt.excluded.close_time_ms,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "is_final": stmt.excluded.is_final,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)
                inserted += len(chunk)
            await session.commit()
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
