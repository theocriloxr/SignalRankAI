"""Cross-process lock for one execution destination per delivered user signal."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

_LOCAL_LOCKS: dict[str, asyncio.Lock] = {}
_LOCAL_LOCKS_GUARD = asyncio.Lock()


def execution_claim_key(user_id: int, signal_id: str) -> str:
    digest = hashlib.sha256(f"{int(user_id)}|{str(signal_id)}".encode()).hexdigest()[:32]
    return f"signalrank:execution-destination:{digest}"


def _production() -> bool:
    value = str(os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("APP_ENV") or "").lower()
    return value in {"production", "prod"}


async def _release_redis_claim(redis_client, key: str, token: str) -> None:
    script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    await asyncio.to_thread(redis_client.eval, script, 1, key, token)


@asynccontextmanager
async def execution_destination_lock(
    user_id: int,
    signal_id: str,
    *,
    timeout_seconds: float = 5.0,
    lease_seconds: int = 180,
) -> AsyncIterator[bool]:
    """Acquire a distributed claim; fail closed in production without Redis."""
    key = execution_claim_key(user_id, signal_id)
    token = uuid.uuid4().hex
    redis_client = None
    try:
        from core.redis_state import state

        redis_client = await asyncio.to_thread(state._get_redis_sync)
    except Exception:
        redis_client = None

    if redis_client is not None:
        acquired = False
        try:
            deadline = asyncio.get_running_loop().time() + max(0.1, float(timeout_seconds))
            while asyncio.get_running_loop().time() < deadline:
                acquired = bool(await asyncio.to_thread(
                    redis_client.set, key, token, ex=max(30, int(lease_seconds)), nx=True
                ))
                if acquired:
                    break
                await asyncio.sleep(0.05)
            yield acquired
        finally:
            if acquired:
                try:
                    await _release_redis_claim(redis_client, key, token)
                except Exception:
                    pass
        return

    if _production():
        yield False
        return

    async with _LOCAL_LOCKS_GUARD:
        local_lock = _LOCAL_LOCKS.setdefault(key, asyncio.Lock())
    acquired = False
    try:
        await asyncio.wait_for(local_lock.acquire(), timeout=max(0.1, float(timeout_seconds)))
        acquired = True
        yield True
    except asyncio.TimeoutError:
        yield False
    finally:
        if acquired and local_lock.locked():
            local_lock.release()
