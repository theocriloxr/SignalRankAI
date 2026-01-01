from __future__ import annotations

import asyncio
import os
import time
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None


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
        self._pg_dsn: Optional[str] = None

    def _redis_url(self) -> Optional[str]:
        url = os.getenv("REDIS_URL")
        return url or None

    def _get_pg_dsn(self) -> Optional[str]:
        if self._pg_dsn is not None:
            return self._pg_dsn
        url = (os.getenv("DATABASE_URL") or "").strip()
        if not url:
            return None
        # psycopg2 expects sync URL. Railway normally provides postgresql:// already.
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._pg_dsn = url
        return self._pg_dsn

    def _pg_available(self) -> bool:
        return psycopg2 is not None and bool(self._get_pg_dsn())

    def _pg_exec_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """Execute a small query against Postgres (sync).

        Opens a short-lived connection for thread-safety across to_thread callers.
        """
        dsn = self._get_pg_dsn()
        if not dsn or psycopg2 is None:
            return None
        try:
            conn = psycopg2.connect(dsn, connect_timeout=3)
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone() if cur.description is not None else None
                    return row
            finally:
                conn.close()
        except Exception:
            return None

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
            # Prefer Postgres-backed shared state when configured.
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value FROM runtime_state WHERE key=%s AND (expires_at IS NULL OR expires_at > NOW())",
                    (_KILL_KEY,),
                )
                if row and row[0] is not None:
                    try:
                        data = row[0]
                        enabled = bool(data.get("enabled", False))
                        reason = str(data.get("reason", ""))
                        updated_at = float(data.get("updated_at", 0.0) or 0.0)
                        return KillSwitchState(enabled, reason, updated_at)
                    except Exception:
                        pass
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
            if self._pg_available():
                data = {"enabled": bool(enabled), "reason": (reason or ""), "updated_at": float(time.time())}
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (%s, %s::jsonb, NULL, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=NULL, updated_at=NOW()",
                    (_KILL_KEY, json.dumps(data)),
                )
                return
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
            if self._pg_available():
                data = {"enabled": True}
                ttl = max(60, int(ttl_seconds))
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, %s::jsonb, NOW() + (%s || ' seconds')::interval, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=EXCLUDED.expires_at, updated_at=NOW()",
                    (key, json.dumps(data), str(ttl)),
                )
                return
            self._memory[key] = time.time() + int(ttl_seconds)
            return
        r.set(key, "1", ex=max(60, int(ttl_seconds)))

    def has_temp_owner_sync(self, telegram_user_id: int) -> bool:
        key = f"signalrankai:owner_bypass:{telegram_user_id}"
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT 1 FROM runtime_state WHERE key=%s AND expires_at > NOW()",
                    (key,),
                )
                return bool(row)
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
            if self._pg_available():
                row = self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, jsonb_build_object('count', 1), NOW() + (%s || ' seconds')::interval, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET "
                    "value = jsonb_build_object('count', "
                    "CASE WHEN runtime_state.expires_at IS NOT NULL AND runtime_state.expires_at > NOW() "
                    "THEN COALESCE((runtime_state.value->>'count')::int, 0) + 1 ELSE 1 END), "
                    "expires_at = EXCLUDED.expires_at, updated_at = NOW() "
                    "RETURNING (value->>'count')::int",
                    (key, str(window)),
                )
                count = int((row or (0,))[0] or 0)
                return count > int(limit)
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
