"""Standalone proof-gated outcome worker role."""
from __future__ import annotations
import asyncio
import contextlib

async def run_async(stop_event: asyncio.Event | None=None) -> None:
    from engine.realtime_outcome_tracker import RealtimeOutcomeTracker
    stop=stop_event or asyncio.Event()
    tracker=RealtimeOutcomeTracker()
    await tracker.start()
    try:
        await stop.wait()
    finally:
        with contextlib.suppress(Exception):
            await tracker.stop()

def run() -> None: asyncio.run(run_async())
start=run
__all__=["run","run_async","start"]
