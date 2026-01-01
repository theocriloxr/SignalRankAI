from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


_KILL_KEY = "signalrankai:killswitch"


@dataclass(frozen=True)
class KillSwitchState:
    enabled: bool
    reason: str
    updated_at: float


class RedisState:
    """Small shared state helper.

    - If `REDIS_URL` is configured and `redis` is installed, uses Redis.
    - Otherwise falls back to process-local memory (local dev only).

    Provides both sync and async APIs:
    - Sync methods are suitable for legacy sync Telegram handlers.
    - Async methods delegate to sync via `asyncio.to_thread`.
    """

    def __init__(self) -> None:
        self._memory: Dict[str, Any] = {}
        self._redis_sync: Any = None

    def _redis_url(self) -> Optional[str]:
        url = os.getenv("REDIS_URL")
        return url or None

    def _get_redis_sync(self):
        if self._redis_sync is not None:
            return self._redis_sync
        url = self._redis_url()
        if not url or redis is None:
            return None

        self._redis_sync = redis.Redis.from_url(url, decode_responses=True)
        return self._redis_sync

    # -------- Sync API (Telegram legacy) --------
    def get_killswitch_sync(self) -> KillSwitchState:
        r = self._get_redis_sync()
        if r is None:
            raw = self._memory.get(_KILL_KEY)
            if not isinstance(raw, dict):
                return KillSwitchState(False, "", 0.0)
            return KillSwitchState(
                bool(raw.get("enabled")),
                str(raw.get("reason", "")),
                float(raw.get("updated_at", 0.0)),
            )

        data = r.hgetall(_KILL_KEY) or {}
        enabled = str(data.get("enabled", "0")) == "1"
        reason = str(data.get("reason", ""))
        updated_at = float(data.get("updated_at", "0"))
        return KillSwitchState(enabled, reason, updated_at)

    def set_killswitch_sync(self, enabled: bool, reason: str = "") -> None:
        payload = {
            "enabled": "1" if enabled else "0",
            "reason": reason or "",
            "updated_at": str(time.time()),
        }
        r = self._get_redis_sync()
        if r is None:
            self._memory[_KILL_KEY] = {
                "enabled": enabled,
                "reason": reason or "",
                "updated_at": time.time(),
            }
            return
        r.hset(_KILL_KEY, mapping=payload)

    def set_temp_owner_sync(self, telegram_user_id: int, ttl_seconds: int) -> None:
        key = f"signalrankai:owner_bypass:{telegram_user_id}"
        r = self._get_redis_sync()
        if r is None:
            self._memory[key] = time.time() + int(ttl_seconds)
            return
        r.set(key, "1", ex=max(60, int(ttl_seconds)))

    def has_temp_owner_sync(self, telegram_user_id: int) -> bool:
        key = f"signalrankai:owner_bypass:{telegram_user_id}"
        r = self._get_redis_sync()
        if r is None:
            exp = self._memory.get(key)
            if not exp:
                return False
            return float(exp) > time.time()
        return r.get(key) == "1"

    def rate_limited_sync(self, telegram_user_id: int, limit: int, window_seconds: int) -> bool:
        """Simple fixed-window rate limit."""
        window = max(1, int(window_seconds))
        key = f"signalrankai:rl:{telegram_user_id}:{int(time.time() // window)}"

        r = self._get_redis_sync()
        if r is None:
            bucket = int(self._memory.get(key, 0)) + 1
            self._memory[key] = bucket
            return bucket > int(limit)

        count = int(r.incr(key))
        if count == 1:
            r.expire(key, window)
        return count > int(limit)

    # -------- Async API (FastAPI/worker) --------
    async def get_killswitch(self) -> KillSwitchState:
        return await asyncio.to_thread(self.get_killswitch_sync)

    async def set_killswitch(self, enabled: bool, reason: str = "") -> None:
        await asyncio.to_thread(self.set_killswitch_sync, enabled, reason)

    async def set_temp_owner(self, telegram_user_id: int, ttl_seconds: int) -> None:
        await asyncio.to_thread(self.set_temp_owner_sync, telegram_user_id, ttl_seconds)

    async def has_temp_owner(self, telegram_user_id: int) -> bool:
        return await asyncio.to_thread(self.has_temp_owner_sync, telegram_user_id)

    async def rate_limited(self, telegram_user_id: int, limit: int, window_seconds: int) -> bool:
        return await asyncio.to_thread(self.rate_limited_sync, telegram_user_id, limit, window_seconds)


state = RedisState()
