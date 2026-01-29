from __future__ import annotations

import asyncio
from config import config
import time
import json
import hashlib
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
_EXTRA_SIGNALS_PREFIX = "signalrankai:extra_signals:"
_DELIVERED_SIGNAL_PREFIX = "signalrankai:delivered_signal:"

def mark_signal_delivered_sync(user_id: int, signal_id: str) -> None:
    """Mark that a signal was delivered to a user. No-op if Redis unavailable."""
    try:
        import redis
        r = redis.Redis()
        key = f"{_DELIVERED_SIGNAL_PREFIX}{user_id}"
        r.sadd(key, signal_id)
    except Exception:
        # Redis not available (dev/railway), skip
        pass

def was_signal_delivered_sync(user_id: int, signal_id: str) -> bool:
    """Check if a signal was delivered to a user. Returns False if Redis unavailable."""
    try:
        import redis
        r = redis.Redis()
        key = f"{_DELIVERED_SIGNAL_PREFIX}{user_id}"
        return r.sismember(key, signal_id)
    except Exception:
        # Redis not available (dev/railway), always return False (so signal will be sent)
        return False

def get_delivered_signals_sync(user_id: int) -> set:
    """Get all signal_ids delivered to a user. Returns empty set if Redis unavailable."""
    try:
        import redis
        r = redis.Redis()
        key = f"{_DELIVERED_SIGNAL_PREFIX}{user_id}"
        return set(r.smembers(key))
    except Exception:
        # Redis not available (dev/railway), return empty set
        return set()


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
        # Redis is intentionally disabled for this project.
        # Shared runtime state is persisted in Postgres (runtime_state table).
        return None

    def _get_pg_dsn(self) -> Optional[str]:
        if self._pg_dsn is not None:
            return self._pg_dsn
        url = (config.DATABASE_URL or "").strip()
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
        # Redis backend disabled: always return None so callers use Postgres or memory.
        return None

    def _bypass_fingerprint(self) -> Optional[str]:
        """Fingerprint the active BYPASS_KEY.

        This lets us invalidate previously granted temp-owner access immediately
        when BYPASS_KEY is rotated, without storing the raw secret.
        """

        key = (os.getenv("BYPASS_KEY") or "").strip()
        if not key:
            return None
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

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
        fp = self._bypass_fingerprint() or ""
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                data = {"enabled": True, "bypass_fp": fp}
                ttl = max(60, int(ttl_seconds))
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, %s::jsonb, NOW() + (%s || ' seconds')::interval, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=EXCLUDED.expires_at, updated_at=NOW()",
                    (key, json.dumps(data), str(ttl)),
                )
                return
            self._memory[key] = {"exp": time.time() + int(ttl_seconds), "bypass_fp": fp}
            return
        r.set(key, f"1:{fp}", ex=max(60, int(ttl_seconds)))

    def has_temp_owner_sync(self, telegram_user_id: int) -> bool:
        key = f"signalrankai:owner_bypass:{telegram_user_id}"
        expected_fp = self._bypass_fingerprint() or ""
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value FROM runtime_state WHERE key=%s AND expires_at > NOW()",
                    (key,),
                )
                if not row or row[0] is None:
                    return False
                try:
                    data = row[0]
                    stored_fp = str(data.get("bypass_fp", "") or "")
                except Exception:
                    stored_fp = ""
                if expected_fp and stored_fp == expected_fp:
                    return True
                # Fingerprint mismatch (or missing): revoke old bypass immediately.
                self._pg_exec_one("DELETE FROM runtime_state WHERE key=%s", (key,))
                return False

            raw = self._memory.get(key)
            if not raw:
                return False
            if isinstance(raw, dict):
                exp = float(raw.get("exp", 0.0) or 0.0)
                stored_fp = str(raw.get("bypass_fp", "") or "")
            else:
                # Legacy in-memory format (timestamp only)
                exp = float(raw)
                stored_fp = ""
            if exp <= time.time():
                return False
            return bool(expected_fp) and stored_fp == expected_fp

        val = r.get(key)
        if not val:
            return False
        if ":" not in val:
            # Legacy format; treat as revoked when we enforce fingerprints.
            try:
                r.delete(key)
            except Exception:
                pass
            return False
        prefix, stored_fp = val.split(":", 1)
        if prefix != "1":
            return False
        if expected_fp and stored_fp == expected_fp:
            return True
        try:
            r.delete(key)
        except Exception:
            pass
        return False

    def add_extra_signals_sync(self, telegram_user_id: int, count: int, ttl_seconds: int = 86400) -> int:
        """Credit extra signals for a free user. Expires after ttl_seconds (default 24h)."""
        uid = int(telegram_user_id)
        count = max(0, int(count))
        if count <= 0:
            return 0
        key = f"{_EXTRA_SIGNALS_PREFIX}{uid}"
        ttl_seconds = max(60, int(ttl_seconds))

        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value, expires_at FROM runtime_state WHERE key=%s AND expires_at > NOW()",
                    (key,),
                )
                total = 0
                used = 0
                if row and row[0] is not None:
                    try:
                        data = row[0]
                        total = int(data.get("total", 0) or 0)
                        used = int(data.get("used", 0) or 0)
                    except Exception:
                        total = 0
                        used = 0
                new_total = total + count
                new_used = used if (row and row[0] is not None) else 0
                payload = {"total": int(new_total), "used": int(new_used)}
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, %s::jsonb, NOW() + (%s || ' seconds')::interval, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=EXCLUDED.expires_at, updated_at=NOW()",
                    (key, json.dumps(payload), str(ttl_seconds)),
                )
                return int(new_total)

            # local dev memory fallback
            existing = self._memory.get(key)
            now = time.time()
            total = 0
            used = 0
            exp = now + ttl_seconds
            if isinstance(existing, dict) and float(existing.get("exp", 0) or 0) > now:
                total = int(existing.get("total", 0) or 0)
                used = int(existing.get("used", 0) or 0)
                exp = float(existing.get("exp", exp) or exp)
            total += count
            self._memory[key] = {"total": int(total), "used": int(used), "exp": float(exp)}
            return int(total)

        # Redis path
        try:
            ttl = r.ttl(key)
        except Exception:
            ttl = -1
        try:
            raw = r.get(key)
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        total = int(data.get("total", 0) or 0)
        used = int(data.get("used", 0) or 0)
        total += count
        payload = json.dumps({"total": int(total), "used": int(used)})
        try:
            r.set(key, payload, ex=(ttl if isinstance(ttl, int) and ttl > 0 else ttl_seconds))
        except Exception:
            pass
        return int(total)

    def get_extra_signals_left_sync(self, telegram_user_id: int) -> int:
        uid = int(telegram_user_id)
        key = f"{_EXTRA_SIGNALS_PREFIX}{uid}"
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value FROM runtime_state WHERE key=%s AND expires_at > NOW()",
                    (key,),
                )
                if not row or row[0] is None:
                    return 0
                try:
                    data = row[0]
                    total = int(data.get("total", 0) or 0)
                    used = int(data.get("used", 0) or 0)
                    return max(0, total - used)
                except Exception:
                    return 0

            existing = self._memory.get(key)
            now = time.time()
            if not isinstance(existing, dict) or float(existing.get("exp", 0) or 0) <= now:
                return 0
            total = int(existing.get("total", 0) or 0)
            used = int(existing.get("used", 0) or 0)
            return max(0, total - used)

        try:
            raw = r.get(key)
            data = json.loads(raw) if raw else {}
            total = int(data.get("total", 0) or 0)
            used = int(data.get("used", 0) or 0)
            return max(0, total - used)
        except Exception:
            return 0

    def consume_extra_signals_sync(self, telegram_user_id: int, amount: int = 1) -> bool:
        uid = int(telegram_user_id)
        amount = max(1, int(amount))
        key = f"{_EXTRA_SIGNALS_PREFIX}{uid}"
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value FROM runtime_state WHERE key=%s AND expires_at > NOW()",
                    (key,),
                )
                if not row or row[0] is None:
                    return False
                try:
                    data = row[0]
                    total = int(data.get("total", 0) or 0)
                    used = int(data.get("used", 0) or 0)
                except Exception:
                    return False
                if total - used < amount:
                    return False
                used += amount
                payload = {"total": int(total), "used": int(used)}
                self._pg_exec_one(
                    "UPDATE runtime_state SET value=%s::jsonb, updated_at=NOW() WHERE key=%s AND expires_at > NOW()",
                    (json.dumps(payload), key),
                )
                return True

            existing = self._memory.get(key)
            now = time.time()
            if not isinstance(existing, dict) or float(existing.get("exp", 0) or 0) <= now:
                return False
            total = int(existing.get("total", 0) or 0)
            used = int(existing.get("used", 0) or 0)
            if total - used < amount:
                return False
            existing["used"] = int(used + amount)
            self._memory[key] = existing
            return True

        try:
            ttl = r.ttl(key)
            raw = r.get(key)
            data = json.loads(raw) if raw else {}
            total = int(data.get("total", 0) or 0)
            used = int(data.get("used", 0) or 0)
            if total - used < amount:
                return False
            used += amount
            payload = json.dumps({"total": int(total), "used": int(used)})
            r.set(key, payload, ex=(ttl if isinstance(ttl, int) and ttl > 0 else 3600))
            return True
        except Exception:
            return False

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
