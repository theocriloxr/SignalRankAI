"""Analytics and learning worker role.

Owns shadow outcomes and bounded all-asset candle collection.  It intentionally
does not own Telegram delivery or live outcome computation.
"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import os
logger=logging.getLogger(__name__)

def _enabled(name: str, default: bool=True) -> bool:
    raw=os.getenv(name); return default if raw is None else raw.strip().lower() in {"1","true","yes","on"}

async def run_async(stop_event: asyncio.Event | None=None) -> None:
    stop=stop_event or asyncio.Event()
    tasks=[]
    shadow=None
    if _enabled("SHADOW_TRACKING_ENABLED", True):
        from engine.shadow_outcome_worker import shadow_outcome_worker
        shadow=shadow_outcome_worker
        await shadow.start()
    if _enabled("ASSET_LEARNING_ENABLED", True):
        from worker.asset_learning_worker import asset_learning_worker
        tasks.append(asyncio.create_task(asset_learning_worker.run(stop),name="asset-learning"))
    if _enabled("ANALYTICS_ML_TRAIN_ENABLED", True):
        async def _ml_loop() -> None:
            delay=max(60, int(os.getenv("ANALYTICS_ML_TRAIN_STARTUP_DELAY_SECONDS", "900") or 900))
            interval=max(3600, int(os.getenv("ML_TRAIN_INTERVAL_SECONDS", "86400") or 86400))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
                return
            except asyncio.TimeoutError:
                pass
            while not stop.is_set():
                try:
                    from ml import train_model as ml_train
                    ok=await ml_train.main()
                    logger.info("[analytics] ml_train status=%s", "success" if ok else "skipped_or_failed")
                except Exception as exc:
                    logger.error("[analytics] ml_train failed err=%s", exc)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        tasks.append(asyncio.create_task(_ml_loop(),name="analytics-ml-train"))
    logger.info("[analytics] started shadow=%s tasks=%s",bool(shadow),[task.get_name() for task in tasks])
    try:
        await stop.wait()
    finally:
        if shadow is not None: await shadow.stop()
        for task in tasks: task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError): await task

def run() -> None: asyncio.run(run_async())
start=run
__all__=["run","run_async","start"]
