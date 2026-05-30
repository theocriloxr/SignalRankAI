"""
engine/shadow_outcome_worker.py

Background worker to track outcomes for `ml_rejected_signals` (shadow tracking).

It marks rejected signals with `actual_outcome` and `outcome_tracked_at` when the
market price reaches a TP or SL. It also increments Redis counters to compute
regret/efficacy metrics used by admin dashboards.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class ShadowOutcomeWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._interval = max(15, int(os.getenv("SHADOW_TRACKER_INTERVAL_SECONDS", "60") or 60))
        self._min_age_minutes = max(1, int(os.getenv("REJECT_OUTCOME_MIN_TRACK_AGE_MINUTES", "5") or 5))

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[shadow_tracker] started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        try:
            self._stop.set()
            if self._task:
                self._task.cancel()
                with contextlib.suppress(Exception):
                    await self._task
        except Exception:
            pass

    async def _run_loop(self) -> None:
        try:
            from db.session import get_session
            from db.models import MLRejectedSignal
            from sqlalchemy import select, update as sa_update
            from engine.realtime_outcome_tracker import _get_live_price, _parse_tp_levels, _check_hit
            from core.redis_state import state

            while not self._stop.is_set():
                try:
                    cutoff = datetime.utcnow() - timedelta(minutes=self._min_age_minutes)
                    async with get_session() as session:
                        stmt = (
                            select(MLRejectedSignal)
                            .where(MLRejectedSignal.outcome_tracked_at.is_(None))
                            .where(MLRejectedSignal.created_at <= cutoff)
                            .order_by(MLRejectedSignal.created_at.asc())
                            .with_for_update(skip_locked=True)
                            .limit(200)
                        )
                        res = await session.execute(stmt)
                        rows = res.scalars().all()
                        await session.commit()

                    for r in rows:
                        try:
                            asset = str(getattr(r, "asset", "") or "")
                            entry = float(getattr(r, "entry", 0.0) or 0.0)
                            sl = float(getattr(r, "stop_loss", 0.0) or 0.0)
                            tp_raw = getattr(r, "take_profit", "")
                            tp_levels = _parse_tp_levels(tp_raw)
                            # fetch live price
                            price = await _get_live_price(asset)
                            if price is None:
                                continue
                            hit = _check_hit(str(getattr(r, "direction", "") or "long"), entry, sl, tp_levels, price)
                            if not hit:
                                continue
                            now = datetime.utcnow()
                            # Claim row only if still untracked, then update outcome.
                            async with get_session() as session:
                                claim = await session.execute(
                                    sa_update(MLRejectedSignal)
                                    .where(MLRejectedSignal.id == int(getattr(r, "id", 0) or 0))
                                    .where(MLRejectedSignal.outcome_tracked_at.is_(None))
                                    .values(actual_outcome=str(hit)[:32], outcome_tracked_at=now)
                                )
                                if int(getattr(claim, "rowcount", 0) or 0) <= 0:
                                    await session.rollback()
                                    continue
                                await session.commit()

                            # classify and increment counters in Redis
                            try:
                                # false_negative: rejected but would have hit TP3 or terminal TP
                                if str(hit).lower().startswith("tp"):
                                    # treat tp3 or generic tp as false negative
                                    if str(hit).lower() in {"tp3", "tp"} or (len(str(hit)) > 3 and int(str(hit)[2:]) >= 3):
                                        state.incr_sync("shadow:counts:false_negative", 1)
                                    else:
                                        # lesser TP hits are partial wins
                                        state.incr_sync("shadow:counts:partial_win", 1)
                                    state.incr_sync("shadow:counts:total_tracked", 1)
                                elif str(hit).lower() == "sl":
                                    # correct block
                                    state.incr_sync("shadow:counts:correct_block", 1)
                                    state.incr_sync("shadow:counts:total_tracked", 1)
                                else:
                                    state.incr_sync("shadow:counts:other_outcome", 1)
                                    state.incr_sync("shadow:counts:total_tracked", 1)
                            except Exception:
                                logger.debug("[shadow_tracker] redis increment failed", exc_info=True)

                        except Exception:
                            logger.debug("[shadow_tracker] row handling failed", exc_info=True)

                except Exception:
                    logger.debug("[shadow_tracker] iteration failed", exc_info=True)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                except asyncio.TimeoutError:
                    continue

        except Exception as exc:
            logger.error("[shadow_tracker] failed: %s", exc, exc_info=True)


shadow_outcome_worker = ShadowOutcomeWorker()
