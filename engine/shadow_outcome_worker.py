"""Track shadow outcomes for rejected and stale signals without blocking delivery.

Rows are loaded in a short background-priority transaction, prices are fetched
after the transaction is closed, and updates are committed in a second short
transaction.  This prevents provider network latency from occupying scarce DB
connections.
"""
from __future__ import annotations
from utils.timeutils import now_utc_naive

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ShadowOutcomeWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._interval = max(15, int(os.getenv("SHADOW_TRACKER_INTERVAL_SECONDS", "60") or 60))
        self._min_age_minutes = max(1, int(os.getenv("REJECT_OUTCOME_MIN_TRACK_AGE_MINUTES", "5") or 5))
        self._batch_size = max(1, min(250, int(os.getenv("SHADOW_TRACKER_BATCH_SIZE", "50") or 50)))
        self._price_concurrency = max(1, min(8, int(os.getenv("SHADOW_PRICE_CONCURRENCY", "3") or 3)))

    def _publish_health(
        self,
        status: str,
        *,
        scanned: int = 0,
        evaluated: int = 0,
        tracked: int = 0,
        error: str | None = None,
    ) -> None:
        """Publish durable proof that the configured tracker is actually running."""
        try:
            import json
            from core.redis_state import state

            payload = {
                "status": str(status),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                "interval_seconds": self._interval,
                "deployment_id": str(os.getenv("RAILWAY_DEPLOYMENT_ID") or "local"),
                "git_sha": str(os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA") or "unknown"),
                "scanned": max(0, int(scanned or 0)),
                "evaluated": max(0, int(evaluated or 0)),
                "tracked": max(0, int(tracked or 0)),
                "error": str(error)[:240] if error else None,
            }
            state.set_sync(
                "shadow:tracker:health",
                json.dumps(payload, sort_keys=True),
                ex=max(300, self._interval * 5),
            )
        except Exception:
            logger.debug("[shadow_tracker] health publication failed", exc_info=True)
    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._publish_health("starting")
        self._task = asyncio.create_task(self._run_loop(), name="shadow-outcome-tracker")
        logger.info("[shadow_tracker] started interval=%ss batch=%s", self._interval, self._batch_size)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._publish_health("stopped")

    async def _load_rows(self) -> list[dict[str, Any]]:
        from db.models import MLRejectedSignal
        from db.priority import DBPriority
        from db.session import NoncriticalWriteDropped, get_session
        from sqlalchemy import select

        cutoff = now_utc_naive() - timedelta(minutes=self._min_age_minutes)
        try:
            async with get_session(priority=DBPriority.BACKGROUND, label="shadow_outcome_scan") as session:
                rows = list((await session.execute(
                    select(MLRejectedSignal)
                    .where(MLRejectedSignal.outcome_tracked_at.is_(None))
                    .where(MLRejectedSignal.created_at <= cutoff)
                    .order_by(MLRejectedSignal.created_at.asc())
                    .limit(self._batch_size)
                )).scalars().all())
                # Copy only primitive values before closing the session.
                return [{
                    "id": int(r.id), "signal_id": r.signal_id, "asset": r.asset,
                    "timeframe": r.timeframe, "direction": r.direction,
                    "entry": float(r.entry or 0.0), "stop_loss": float(r.stop_loss or 0.0),
                    "take_profit": r.take_profit, "ml_probability": float(r.ml_probability or 0.0),
                    "rejection_reason": r.rejection_reason, "features": dict(r.features or {}),
                } for r in rows]
        except NoncriticalWriteDropped:
            logger.info("[shadow_tracker] deferred reason=db_background_capacity")
            return []

    async def _evaluate_rows(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
        from engine.realtime_outcome_tracker import _check_hit, _get_live_price, _parse_tp_levels
        semaphore = asyncio.Semaphore(self._price_concurrency)

        async def one(row: dict[str, Any]):
            async with semaphore:
                price = await _get_live_price(str(row["asset"]))
            if price is None:
                return None
            hit = _check_hit(
                str(row["direction"]), float(row["entry"]), float(row["stop_loss"]),
                _parse_tp_levels(row["take_profit"]), float(price),
            )
            return (row, str(hit).lower()) if hit else None

        results = await asyncio.gather(*(one(row) for row in rows), return_exceptions=True)
        return [item for item in results if isinstance(item, tuple)]

    async def _persist(self, evaluated: list[tuple[dict[str, Any], str]]) -> int:
        if not evaluated:
            return 0
        from core.redis_state import state
        from db.models import MLRejectedSignal, MLShadowPrediction
        from db.priority import DBPriority
        from db.session import NoncriticalWriteDropped, get_session
        from sqlalchemy import select

        ids = [row["id"] for row, _ in evaluated]
        by_id = {row["id"]: (row, outcome) for row, outcome in evaluated}
        now = now_utc_naive()
        try:
            async with get_session(priority=DBPriority.BACKGROUND, label="shadow_outcome_write") as session:
                db_rows = list((await session.execute(
                    select(MLRejectedSignal).where(MLRejectedSignal.id.in_(ids)).with_for_update(skip_locked=True)
                )).scalars().all())
                tracked = 0
                for record in db_rows:
                    source, outcome = by_id.get(int(record.id), ({}, ""))
                    if not outcome or record.outcome_tracked_at is not None:
                        continue
                    session.add(MLShadowPrediction(
                        signal_id=source.get("signal_id"),
                        model_name="rejection_outcome_tracker",
                        model_version=os.getenv("ML_MODEL_VERSION", "v1"),
                        probability=float(source.get("ml_probability") or 0.0),
                        is_shadow=True, feature_schema_ok=True,
                        meta={
                            "asset": source.get("asset"), "direction": source.get("direction"),
                            "entry": source.get("entry"), "stop_loss": source.get("stop_loss"),
                            "take_profit": str(source.get("take_profit")), "actual_outcome": outcome,
                            "rejection_reason": source.get("rejection_reason"),
                            "learning_category": (source.get("features") or {}).get("learning_category", "SHADOW_REJECTED"),
                            "rejection_id": int(record.id),
                        }, created_at=now,
                    ))
                    record.actual_outcome = outcome[:32]
                    record.outcome_tracked_at = now
                    tracked += 1
                    try:
                        bucket = "false_negative" if outcome.startswith("tp") else "correct_block" if outcome == "sl" else "other_outcome"
                        state.incr_sync(f"shadow:counts:{bucket}", 1)
                        state.incr_sync("shadow:counts:total_tracked", 1)
                    except Exception:
                        logger.debug("[shadow_tracker] redis metric failed", exc_info=True)
                await session.commit()
                return tracked
        except NoncriticalWriteDropped:
            logger.info("[shadow_tracker] write deferred reason=db_background_capacity")
            return 0

    async def run_once(self) -> int:
        rows = await self._load_rows()
        if not rows:
            self._publish_health("idle")
            return 0
        evaluated = await self._evaluate_rows(rows)
        tracked = await self._persist(evaluated)
        self._publish_health(
            "healthy",
            scanned=len(rows),
            evaluated=len(evaluated),
            tracked=tracked,
        )
        if tracked:
            logger.info("[shadow_tracker] processed=%s scanned=%s", tracked, len(rows))
        return tracked

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[shadow_tracker] iteration failed: %s", exc, exc_info=True)
                self._publish_health("degraded", error=f"{type(exc).__name__}: {exc}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass


shadow_outcome_worker = ShadowOutcomeWorker()
