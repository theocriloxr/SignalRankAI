"""Analytics-worker role adapter.

Analytics jobs are intentionally opt-in during decomposition.  The bounded
adapter keeps the role explicit and provides a cooperative idle loop until the
outbox/analytics worker becomes its own implementation.
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
