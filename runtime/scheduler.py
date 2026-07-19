"""Scheduler role adapter.

The legacy Railway app still owns scheduler registration.  This adapter is a
safe hand-off point for a future singleton scheduler lease and remains idle
until that ownership switch is enabled explicitly.
"""

from __future__ import annotations

import asyncio


async def run_async(stop_event: asyncio.Event | None = None) -> None:
    event = stop_event or asyncio.Event()
    while not event.is_set():
        try:
            await asyncio.wait_for(event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            continue


def run() -> None:
    asyncio.run(run_async())


start = run

__all__ = ["run", "run_async", "start"]
