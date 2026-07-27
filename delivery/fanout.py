"""Deterministic, restart-friendly delivery fanout planning.

This module performs no Telegram or database I/O. It converts an eligible user
set into stable shards and bounded batches, allowing queue workers to resume
without creating one coroutine for every recipient.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from typing import Iterable, Iterator


@dataclass(frozen=True, slots=True)
class DeliveryBatch:
    shard: int
    batch_index: int
    user_ids: tuple[int, ...]

    @property
    def idempotency_key(self) -> str:
        payload = f"{self.shard}|{self.batch_index}|" + ",".join(map(str, self.user_ids))
        return blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def delivery_shard(user_id: int, shard_count: int) -> int:
    count = max(1, int(shard_count))
    digest = blake2b(str(int(user_id)).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % count


def iter_delivery_batches(
    user_ids: Iterable[int],
    *,
    shard_count: int = 16,
    batch_size: int = 100,
) -> Iterator[DeliveryBatch]:
    """Yield stable, duplicate-free batches ordered by shard then user ID."""
    shards: dict[int, list[int]] = {idx: [] for idx in range(max(1, int(shard_count)))}
    seen: set[int] = set()
    for raw_user_id in user_ids:
        user_id = int(raw_user_id)
        if user_id in seen:
            continue
        seen.add(user_id)
        shards[delivery_shard(user_id, len(shards))].append(user_id)

    size = max(1, int(batch_size))
    for shard in sorted(shards):
        ordered = sorted(shards[shard])
        for offset in range(0, len(ordered), size):
            yield DeliveryBatch(shard, offset // size, tuple(ordered[offset : offset + size]))


__all__ = ["DeliveryBatch", "delivery_shard", "iter_delivery_batches"]
