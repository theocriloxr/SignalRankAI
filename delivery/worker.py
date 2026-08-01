"""Recovery worker for accepted Telegram responses awaiting DB proof."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from delivery.receipts import DeliveryReceipt, ReceiptStore, receipt_store

logger = logging.getLogger(__name__)


async def reconcile_delivery_receipt(receipt: DeliveryReceipt, *, store: ReceiptStore = receipt_store) -> bool:
    """Persist one stashed acknowledgement and its active-message pointer."""
    from db.pg_features import mark_signal_delivery_result
    from db.priority import DBPriority
    from db.session import get_session

    proof = {
        "mode": receipt.mode,
        "chat_id": receipt.operation.channel_id,
        "message_id": receipt.message_id,
        "delivery_receipt": receipt.as_dict(),
        "receipt_stashed": True,
    }
    if receipt.replaces_signal_id:
        proof["edited_old_signal_id"] = receipt.replaces_signal_id
    timeout_seconds = max(
        3.0,
        float(os.getenv("DELIVERY_RECONCILE_DB_TIMEOUT_SECONDS", "10") or 10),
    )

    async def _persist() -> bool:
        async with get_session(
            priority=DBPriority.INTERACTIVE,
            label="delivery_receipt_reconcile",
            timeout_seconds=timeout_seconds,
        ) as session:
            persisted = await mark_signal_delivery_result(
                session,
                telegram_user_id=receipt.operation.user_id,
                signal_id=receipt.operation.signal_id,
                sent_ok=True,
                telegram_chat_id=receipt.operation.channel_id,
                telegram_message_id=receipt.message_id,
                telegram_api_result=proof,
                delivery_state="RECONCILED",
            )
            if not persisted:
                await session.rollback()
                return False
            await session.commit()
        await store.acknowledge(receipt)
        logger.info(
            "[delivery_receipt_reconciled] key=%s user=%s signal=%s message_id=%s",
            receipt.idempotency_key,
            receipt.operation.user_id,
            receipt.operation.signal_id,
            receipt.message_id,
        )
        return True

    try:
        return bool(await asyncio.wait_for(_persist(), timeout=timeout_seconds + 1.0))
    except asyncio.TimeoutError:
        logger.warning(
            "[delivery_receipt_reconcile_timeout] key=%s user=%s signal=%s timeout=%.1fs",
            receipt.idempotency_key,
            receipt.operation.user_id,
            receipt.operation.signal_id,
            timeout_seconds,
        )
        return False
    except Exception as exc:
        logger.warning(
            "[delivery_receipt_reconcile_failed] key=%s user=%s signal=%s err=%s",
            receipt.idempotency_key,
            receipt.operation.user_id,
            receipt.operation.signal_id,
            exc,
        )
        return False


async def reconcile_delivery_receipts_once(
    *,
    store: ReceiptStore = receipt_store,
    limit: int | None = None,
) -> dict[str, int]:
    batch_limit = max(1, int(limit or os.getenv("DELIVERY_RECONCILE_BATCH_SIZE", "100") or 100))
    receipts = await store.pending(limit=batch_limit)
    repaired = 0
    for receipt in receipts:
        if await reconcile_delivery_receipt(receipt, store=store):
            repaired += 1
    return {"found": len(receipts), "reconciled": repaired, "pending": len(receipts) - repaired}


async def delivery_receipt_reconciler_loop(
    *,
    store: ReceiptStore = receipt_store,
    stop_event: asyncio.Event | None = None,
) -> None:
    interval = max(5.0, float(os.getenv("DELIVERY_RECONCILE_INTERVAL_SECONDS", "30") or 30))
    startup_delay = max(
        0.0,
        float(os.getenv("DELIVERY_RECONCILE_STARTUP_DELAY_SECONDS", "30") or 30),
    )
    if startup_delay:
        try:
            if stop_event is None:
                await asyncio.sleep(startup_delay)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=startup_delay)
                return
        except asyncio.TimeoutError:
            pass
    while stop_event is None or not stop_event.is_set():
        try:
            result = await reconcile_delivery_receipts_once(store=store)
            if result["found"]:
                logger.info("[delivery_receipt_reconcile_cycle] %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[delivery_receipt_reconcile_cycle_failed] err=%s", exc)
        try:
            if stop_event is None:
                await asyncio.sleep(interval)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def start_delivery_receipt_reconciler(app: Any) -> asyncio.Task:
    """Start one app-owned loop and retain the handle for graceful shutdown."""
    existing = app.bot_data.get("delivery_receipt_reconciler_task")
    if existing is not None and not existing.done():
        return existing
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        delivery_receipt_reconciler_loop(stop_event=stop_event),
        name="delivery-receipt-reconciler",
    )
    app.bot_data["delivery_receipt_reconciler_stop"] = stop_event
    app.bot_data["delivery_receipt_reconciler_task"] = task
    return task


async def stop_delivery_receipt_reconciler(app: Any) -> None:
    stop_event = app.bot_data.get("delivery_receipt_reconciler_stop")
    task = app.bot_data.get("delivery_receipt_reconciler_task")
    if stop_event is not None:
        stop_event.set()
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
