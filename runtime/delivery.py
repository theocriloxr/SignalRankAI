"""Delivery-worker role adapter.

Pass 3's receipt reconciler is the durable implementation currently available;
the adapter exposes it as a role without importing Telegram at process start.
"""

from __future__ import annotations

import asyncio


async def run_async(stop_event: asyncio.Event | None = None) -> None:
    from delivery.worker import delivery_receipt_reconciler_loop

    await delivery_receipt_reconciler_loop(stop_event=stop_event)


def run() -> None:
    asyncio.run(run_async())


start = run

__all__ = ["run", "run_async", "start"]
