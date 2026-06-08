"""
engine/shadow_outcome_worker.py

Background worker to track outcomes for `ml_rejected_signals` (shadow tracking).
Optimized for batch commits and fixed logic for outcome classification.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Optional

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
            # Local imports to prevent circular dependency issues in some engine architectures
            from db.session import get_session
            from db.models import MLRejectedSignal, MLShadowPrediction
            from sqlalchemy import select
            from engine.realtime_outcome_tracker import _get_live_price, _parse_tp_levels, _check_hit
            from core.redis_state import state

            while not self._stop.is_set():
                try:
                    cutoff = datetime.utcnow() - timedelta(minutes=self._min_age_minutes)
                    
                    async with get_session() as session:
                        # 1. Fetch a batch of untracked signals
                        stmt = (
                            select(MLRejectedSignal)
                            .where(MLRejectedSignal.outcome_tracked_at.is_(None))
                            .where(MLRejectedSignal.created_at <= cutoff)
                            .order_by(MLRejectedSignal.created_at.asc())
                            .with_for_update(skip_locked=True)
                            .limit(100) # Slightly smaller batch for better transaction stability
                        )
                        res = await session.execute(stmt)
                        rows = res.scalars().all()

                        if not rows:
                            # No work to do, release session and wait
                            await session.commit()
                        else:
                            for r in rows:
                                try:
                                    asset = str(getattr(r, "asset", "") or "")
                                    entry = float(getattr(r, "entry", 0.0) or 0.0)
                                    sl = float(getattr(r, "stop_loss", 0.0) or 0.0)
                                    tp_raw = getattr(r, "take_profit", "")
                                    tp_levels = _parse_tp_levels(tp_raw)
                                    direction = str(getattr(r, "direction", "") or "long")

                                    # Fetch live price
                                    price = await _get_live_price(asset)
                                    if price is None:
                                        continue
                                    
                                    # Check if TP or SL has been hit
                                    hit = _check_hit(direction, entry, sl, tp_levels, price)
                                    if not hit:
                                        continue

                                    now = datetime.utcnow()
                                    actual_outcome = str(hit).lower()
                                    
                                    # Resolve Signal ID
                                    signal_id = getattr(r, "signal_id", None)
                                    if signal_id is None:
                                        features = getattr(r, "features", {}) or {}
                                        signal_id = features.get("signal_id")

                                    # 2. Prepare the MLShadowPrediction record
                                    shadow_pred = MLShadowPrediction(
                                        signal_id=signal_id,
                                        model_name="xgboost_rejection_validator",
                                        model_version=os.getenv("ML_MODEL_VERSION", "v1"),
                                        probability=float(getattr(r, "ml_probability", 0.0) or 0.0),
                                        is_shadow=True,
                                        feature_schema_ok=True,
                                        meta={
                                            "asset": asset,
                                            "direction": direction,
                                            "entry": entry,
                                            "stop_loss": sl,
                                            "take_profit": str(tp_raw),
                                            "actual_outcome": actual_outcome,
                                            "rejection_reason": str(getattr(r, "rejection_reason", "") or ""),
                                            "rejection_id": int(getattr(r, "id", 0) or 0),
                                        },
                                        created_at=now,
                                    )
                                    session.add(shadow_pred)

                                    # 3. Update the existing RejectedSignal record
                                    r.actual_outcome = actual_outcome[:32]
                                    r.outcome_tracked_at = now

                                    # 4. Update Redis Metrics
                                    try:
                                        if actual_outcome.startswith("tp"):
                                            # Classification logic: TP3+ is a False Negative (we should have taken it)
                                            is_high_tp = actual_outcome in {"tp3", "tp"}
                                            if not is_high_tp and len(actual_outcome) > 2:
                                                suffix = actual_outcome[2:]
                                                if suffix.isdigit() and int(suffix) >= 3:
                                                    is_high_tp = True

                                            if is_high_tp:
                                                state.incr_sync("shadow:counts:false_negative", 1)
                                            else:
                                                state.incr_sync("shadow:counts:partial_win", 1)
                                        
                                        elif actual_outcome == "sl":
                                            # Correct block: Rejection saved us from a loss
                                            state.incr_sync("shadow:counts:correct_block", 1)
                                        else:
                                            state.incr_sync("shadow:counts:other_outcome", 1)
                                        
                                        state.incr_sync("shadow:counts:total_tracked", 1)
                                    except Exception:
                                        logger.debug("[shadow_tracker] redis increment failed", exc_info=True)

                                except Exception as row_err:
                                    logger.error(f"[shadow_tracker] failed processing row {getattr(r, 'id', '?')}: {row_err}")

                            # Commit all changes for this batch at once
                            await session.commit()
                            logger.info(f"[shadow_tracker] Processed batch of {len(rows)} signals")

                except Exception as iter_err:
                    logger.error(f"[shadow_tracker] iteration failed: {iter_err}")
                    logger.error(traceback.format_exc())

                # Sleep until next interval
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                except asyncio.TimeoutError:
                    continue

        except Exception as exc:
            logger.error("[shadow_tracker] critical failure: %s", exc, exc_info=True)


shadow_outcome_worker = ShadowOutcomeWorker()