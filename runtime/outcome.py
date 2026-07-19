"""Outcome-worker role adapter."""

from __future__ import annotations

import asyncio


async def run_async() -> None:
    from engine.realtime_outcome_tracker import RealtimeOutcomeTracker

    tracker = RealtimeOutcomeTracker()
    await tracker.start()


def run() -> None:
    asyncio.run(run_async())


start = run

__all__ = ["run", "run_async", "start"]
