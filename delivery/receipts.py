"""Telegram acknowledgement receipt stash.

Accepted Bot API responses are copied to Redis before the delivery call
returns.  Redis is a recovery projection only; PostgreSQL ``signal_deliveries``
remains the durable source of truth after proof reconciliation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from delivery.service import DeliveryOperation

logger = logging.getLogger(__name__)

_RECEIPT_PREFIX = "delivery:receipt:v1:"
_PENDING_INDEX = "delivery:receipts:pending:v1"


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    operation: DeliveryOperation
    message_id: int
    mode: str
    accepted_at: str
    replaces_signal_id: str | None = None

    @classmethod
    def accepted(
        cls,
        operation: DeliveryOperation,
        *,
        message_id: int,
        mode: str,
        replaces_signal_id: str | None = None,
    ) -> "DeliveryReceipt":
        return cls(
            operation=operation,
            message_id=int(message_id),
            mode=str(mode or "sent"),
            accepted_at=datetime.now(timezone.utc).isoformat(),
            replaces_signal_id=(str(replaces_signal_id).strip() if replaces_signal_id else None),
        )

    @property
    def idempotency_key(self) -> str:
        return self.operation.idempotency_key

    @property
    def redis_key(self) -> str:
        return f"{_RECEIPT_PREFIX}{self.idempotency_key}"

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.operation.as_dict(),
            "message_id": self.message_id,
            "mode": self.mode,
            "accepted_at": self.accepted_at,
            "replaces_signal_id": self.replaces_signal_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DeliveryReceipt":
        operation = DeliveryOperation(
            user_id=int(value["user_id"]),
            signal_id=str(value["signal_id"]),
            channel_id=int(value["channel_id"]),
            signal_version=str(value.get("signal_version") or "1"),
            delivery_kind=str(value.get("delivery_kind") or "signal"),
        )
        expected_key = operation.idempotency_key
        supplied_key = str(value.get("idempotency_key") or expected_key)
        if supplied_key != expected_key:
            raise ValueError("delivery receipt idempotency key does not match its operation")
        return cls(
            operation=operation,
            message_id=int(value["message_id"]),
            mode=str(value.get("mode") or "sent"),
            accepted_at=str(value.get("accepted_at") or ""),
            replaces_signal_id=(
                str(value.get("replaces_signal_id")).strip()
                if value.get("replaces_signal_id")
                else None
            ),
        )


class ReceiptStore:
    """Small Redis-backed receipt store with an enumerable pending index."""

    def __init__(self, redis_state: Any | None = None) -> None:
        if redis_state is None:
            from core.redis_state import state as redis_state
        self._state = redis_state
        self._ttl_seconds = max(
            3600,
            int(os.getenv("DELIVERY_RECEIPT_TTL_SECONDS", str(7 * 24 * 3600)) or 7 * 24 * 3600),
        )

    def _redis(self) -> Any | None:
        getter = getattr(self._state, "_get_redis_sync", None)
        return getter() if callable(getter) else None

    def stash_sync(self, receipt: DeliveryReceipt) -> bool:
        client = self._redis()
        if client is None:
            logger.warning(
                "[delivery_receipt_stash_unavailable] key=%s user=%s signal=%s",
                receipt.idempotency_key,
                receipt.operation.user_id,
                receipt.operation.signal_id,
            )
            return False
        payload = json.dumps(receipt.as_dict(), sort_keys=True, separators=(",", ":"))
        try:
            pipe = client.pipeline(transaction=True)
            pipe.set(receipt.redis_key, payload, ex=self._ttl_seconds)
            pipe.sadd(_PENDING_INDEX, receipt.redis_key)
            pipe.expire(_PENDING_INDEX, self._ttl_seconds + 3600)
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning(
                "[delivery_receipt_stash_failed] key=%s err=%s",
                receipt.idempotency_key,
                exc,
            )
            return False

    async def stash(self, receipt: DeliveryReceipt) -> bool:
        return bool(await asyncio.to_thread(self.stash_sync, receipt))

    def pending_sync(self, *, limit: int = 100) -> list[DeliveryReceipt]:
        client = self._redis()
        if client is None:
            return []
        try:
            keys: Iterable[str] = client.smembers(_PENDING_INDEX) or ()
        except Exception as exc:
            logger.warning("[delivery_receipt_list_failed] err=%s", exc)
            return []
        receipts: list[DeliveryReceipt] = []
        for key in sorted(str(item) for item in keys)[: max(0, int(limit))]:
            try:
                raw = client.get(key)
                if raw is None:
                    client.srem(_PENDING_INDEX, key)
                    continue
                receipts.append(DeliveryReceipt.from_dict(json.loads(raw)))
            except Exception as exc:
                logger.warning("[delivery_receipt_invalid] key=%s err=%s", key, exc)
        return receipts

    async def pending(self, *, limit: int = 100) -> list[DeliveryReceipt]:
        return await asyncio.to_thread(self.pending_sync, limit=limit)

    def acknowledge_sync(self, receipt: DeliveryReceipt) -> bool:
        client = self._redis()
        if client is None:
            return False
        try:
            pipe = client.pipeline(transaction=True)
            pipe.delete(receipt.redis_key)
            pipe.srem(_PENDING_INDEX, receipt.redis_key)
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning(
                "[delivery_receipt_ack_failed] key=%s err=%s",
                receipt.idempotency_key,
                exc,
            )
            return False

    async def acknowledge(self, receipt: DeliveryReceipt) -> bool:
        return bool(await asyncio.to_thread(self.acknowledge_sync, receipt))


receipt_store = ReceiptStore()
