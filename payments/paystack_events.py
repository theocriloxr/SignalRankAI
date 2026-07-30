"""Durable Paystack webhook inbox and recovery worker.

Ingress stores the signed provider payload before acknowledging it. Processing
is idempotent and recoverable after a process crash because pending/failed
records are retried by the worker.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Mapping

from db.repository import (
    get_webhook_event,
    list_recoverable_webhook_events,
    mark_webhook_event_processed,
    paystack_event_identity,
    update_webhook_event_status,
)
from db.session import get_session, is_db_configured

logger = logging.getLogger(__name__)


class PaystackInboxError(RuntimeError):
    pass


async def ingest_paystack_event(
    payload: Mapping[str, Any],
    raw_body: bytes,
    *,
    route: str,
) -> dict[str, Any]:
    if not is_db_configured():
        raise PaystackInboxError("paystack_webhook_database_required")
    body = dict(payload or {})
    event_type = str(body.get("event") or "unknown").strip() or "unknown"
    data = dict(body.get("data") or {}) if isinstance(body.get("data"), Mapping) else {}
    reference = str(data.get("reference") or "").strip() or None
    event_id, payload_hash = paystack_event_identity(body, raw_body)

    created = False
    async with get_session(label="paystack.inbox", timeout_seconds=8.0) as session:
        existing = await get_webhook_event(session, event_id)
        if existing is None:
            created = await mark_webhook_event_processed(
                session,
                provider="paystack",
                event_id=event_id,
                event_type=event_type,
                reference=reference,
                payload_hash=payload_hash,
                meta={"route": str(route), "payload": body},
            )
            if created:
                await session.commit()
            else:
                existing = await get_webhook_event(session, event_id)
        if existing is not None:
            if str(existing.payload_hash) != payload_hash:
                raise PaystackInboxError("paystack_event_identity_payload_mismatch")
            existing.meta = {**dict(existing.meta or {}), "route": str(route), "payload": body}
            await session.commit()
            status = str(existing.status or "pending")
        else:
            status = "pending"
    return {
        "event_id": event_id,
        "status": status,
        "created": created,
        "idempotent": not created,
        "terminal": status in {"succeeded", "ignored"},
    }


async def process_stored_paystack_event(event_id: str) -> dict[str, Any]:
    payload: dict[str, Any]
    async with get_session(label="paystack.claim", timeout_seconds=8.0) as session:
        row = await get_webhook_event(session, event_id)
        if row is None:
            raise PaystackInboxError("paystack_event_not_found")
        current = str(row.status or "pending")
        if current in {"succeeded", "ignored"}:
            return {"processed": current == "succeeded", "ignored": current == "ignored", "idempotent": True}
        max_attempts = max(1, int(os.getenv("PAYSTACK_WEBHOOK_MAX_ATTEMPTS", "10") or 10))
        if int(row.attempt_count or 0) >= max_attempts:
            return {"processed": False, "reason": "maximum_attempts_exceeded"}
        payload = dict((row.meta or {}).get("payload") or {})
        if not payload:
            await update_webhook_event_status(
                session, event_id=event_id, status="failed", error="stored_payload_missing", increment_attempt=True
            )
            await session.commit()
            return {"processed": False, "reason": "stored_payload_missing"}
        await update_webhook_event_status(
            session, event_id=event_id, status="processing", increment_attempt=True
        )
        await session.commit()

    try:
        from payments.paystack import process_event

        result = dict(await process_event(payload) or {})
        if result.get("processed"):
            status = "succeeded"
            error = None
        elif result.get("ignored"):
            status = "ignored"
            error = None
        else:
            status = "failed"
            error = str(result.get("reason") or "payment_event_processing_failed")
    except Exception as exc:
        logger.exception("[paystack_inbox] processing failed event_id=%s", event_id)
        result = {"processed": False, "reason": f"{type(exc).__name__}:{exc}"}
        status = "failed"
        error = str(result["reason"])

    async with get_session(label="paystack.complete", timeout_seconds=8.0) as session:
        await update_webhook_event_status(
            session, event_id=event_id, status=status, error=error, increment_attempt=False
        )
        await session.commit()
    return result


async def recover_paystack_events_once() -> int:
    if not is_db_configured():
        return 0
    max_attempts = max(1, int(os.getenv("PAYSTACK_WEBHOOK_MAX_ATTEMPTS", "10") or 10))
    async with get_session(label="paystack.recovery.list", timeout_seconds=8.0) as session:
        rows = await list_recoverable_webhook_events(
            session,
            provider="paystack",
            max_attempts=max_attempts,
            limit=max(1, int(os.getenv("PAYSTACK_WEBHOOK_RECOVERY_BATCH", "25") or 25)),
        )
        event_ids = [str(row.event_id) for row in rows]
    processed = 0
    for event_id in event_ids:
        await process_stored_paystack_event(event_id)
        processed += 1
    return processed


async def paystack_webhook_recovery_loop(stop_event: asyncio.Event) -> None:
    interval = max(15.0, float(os.getenv("PAYSTACK_WEBHOOK_RECOVERY_INTERVAL_SECONDS", "60") or 60))
    while not stop_event.is_set():
        try:
            count = await recover_paystack_events_once()
            if count:
                logger.info("[paystack_inbox] recovered events=%s", count)
        except Exception as exc:
            logger.warning("[paystack_inbox] recovery cycle failed: %s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


__all__ = [
    "PaystackInboxError",
    "ingest_paystack_event",
    "paystack_webhook_recovery_loop",
    "process_stored_paystack_event",
    "recover_paystack_events_once",
]
