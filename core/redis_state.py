from __future__ import annotations

import asyncio
from config import config
import time
import json
import hashlib
import os
import threading
from collections import OrderedDict
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
        self._cache_max = int(os.getenv("STATE_CACHE_MAX_KEYS", "4096") or 4096)
        self._cache: "OrderedDict[str, tuple[Any, float | None]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._pending_writes: Dict[str, tuple[str, Optional[int]]] = {}
        self._pending_lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._flush_stop = threading.Event()
        self._flush_interval = max(1, int(os.getenv("STATE_FLUSH_INTERVAL_SECONDS", "3") or 3))
        self._ensure_flush_worker()

    def _redis_url(self) -> Optional[str]:
        # Redis is intentionally disabled for this project.
        # Shared runtime state is persisted in Postgres (runtime_state table).
        return None

    def _get_pg_dsn(self) -> Optional[str]:
        if self._pg_dsn is not None:
            return self._pg_dsn
        # Read fresh from env on every first call — never use a stale import-time
        # snapshot from config.DATABASE_URL. Prefer DATABASE_PUBLIC_URL (Railway's
        # external IPv4 proxy) to avoid IPv6 ECONNREFUSED.
        url = (
            os.getenv("DATABASE_PUBLIC_URL")
            or os.getenv("DATABASE_URL")
            or (getattr(config, "DATABASE_URL", None) or "")
        ).strip()
        if not url:
            return None
        # psycopg2 expects a sync URL — strip asyncpg dialect and normalise scheme.
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif url.startswith("postgres://"):
            # Some providers emit the short 'postgres://' scheme; psycopg2 ≥ 2.9
            # handles it but older versions don't — normalise to be safe.
            url = url.replace("postgres://", "postgresql://", 1)
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

    def _cache_get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._cache_lock:
            rec = self._cache.get(key)
            if not rec:
                return None
            val, exp = rec
            if exp is not None and exp <= now:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return val

    def _cache_set(self, key: str, val: Any, ex: Optional[int] = None) -> None:
        expiry = (time.time() + int(ex)) if ex else None
        with self._cache_lock:
            self._cache[key] = (val, expiry)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    def _enqueue_write(self, key: str, value: str, ex: Optional[int]) -> None:
        with self._pending_lock:
            self._pending_writes[key] = (str(value), ex)

    def _flush_pending_once(self) -> None:
        if not self._pg_available():
            return
        with self._pending_lock:
            if not self._pending_writes:
                return
            batch = dict(self._pending_writes)
            self._pending_writes.clear()
        for key, (value, ex) in batch.items():
            data = {"value": str(value)}
            if ex:
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, %s::jsonb, NOW() + (%s || ' seconds')::interval, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=EXCLUDED.expires_at, updated_at=NOW()",
                    (key, json.dumps(data), str(ex)),
                )
            else:
                self._pg_exec_one(
                    "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                    "VALUES (%s, %s::jsonb, NULL, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, expires_at=NULL, updated_at=NOW()",
                    (key, json.dumps(data)),
                )

    def _flush_loop(self) -> None:
        while not self._flush_stop.is_set():
            try:
                self._flush_pending_once()
            except Exception:
                pass
            self._flush_stop.wait(self._flush_interval)

    def _ensure_flush_worker(self) -> None:
        if self._flush_thread and self._flush_thread.is_alive():
            return
        self._flush_stop.clear()
        self._flush_thread = threading.Thread(target=self._flush_loop, name="state-flush-worker", daemon=True)
        self._flush_thread.start()

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
                    except Exception as e:
                        import logging
                        logging.debug(f"[redis_state] Failed to parse killswitch state from Postgres: {e}")
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
            except Exception as e:
                import logging
                logging.debug(f"[redis_state] Failed to delete legacy temp owner key: {e}")
                pass
            return False
        prefix, stored_fp = val.split(":", 1)
        if prefix != "1":
            return False
        if expected_fp and stored_fp == expected_fp:
            return True
        try:
            r.delete(key)
        except Exception as e:
            import logging
            logging.debug(f"[redis_state] Failed to delete mismatched temp owner key: {e}")
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
        except Exception as e:
            import logging
            logging.debug(f"[redis_state] Failed to set extra signals in Redis: {e}")
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
        cached_hits = self._cache_get(key)
        if cached_hits is not None:
            try:
                hits = int(cached_hits) + 1
            except Exception:
                hits = 1
            self._cache_set(key, hits, ex=window)
            return hits > int(limit)

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
                self._cache_set(key, count, ex=window)
                return count > int(limit)
            bucket = int(self._memory.get(key, 0)) + 1
            self._memory[key] = bucket
            self._cache_set(key, bucket, ex=window)
            return bucket > int(limit)

        count = int(r.incr(key))
        if count == 1:
            r.expire(key, window)
        self._cache_set(key, count, ex=window)
        return count > int(limit)

    def get_sync(self, key: str) -> Optional[str]:
        """Get a value from the state store (Postgres or memory)."""
        cached = self._cache_get(key)
        if cached is not None:
            return str(cached)
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                row = self._pg_exec_one(
                    "SELECT value FROM runtime_state WHERE key=%s AND (expires_at IS NULL OR expires_at > NOW())",
                    (key,),
                )
                if row and row[0] is not None:
                    try:
                        # If it's a dict, try to get a 'value' field, otherwise convert to string
                        data = row[0]
                        if isinstance(data, dict):
                            out = str(data.get('value', ''))
                            self._cache_set(key, out, ex=30)
                            return out
                        out = str(data)
                        self._cache_set(key, out, ex=30)
                        return out
                    except Exception as e:
                        import logging
                        logging.warning(f"[redis_state] Failed to parse value for key {key}: {e}")
                        return None
                return None
            # Memory fallback
            return self._memory.get(key)
        # Redis path (not used in this project)
        try:
            val = r.get(key)
            out = val.decode('utf-8') if isinstance(val, bytes) else val
            self._cache_set(key, out, ex=30)
            return out
        except Exception as e:
            import logging
            logging.warning(f"[redis_state] Failed to get key {key} from Redis: {e}")
            return None

    def set_sync(self, key: str, value: str, ex: Optional[int] = None) -> None:
        """Set a value in the state store (Postgres or memory) with optional expiration."""
        self._cache_set(key, str(value), ex=ex or 30)
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                self._enqueue_write(key, str(value), ex)
                return
            # Memory fallback
            self._memory[key] = str(value)
            return
        # Redis path (not used in this project)
        try:
            if ex:
                r.set(key, str(value), ex=ex)
            else:
                r.set(key, str(value))
        except Exception as e:
            import logging
            logging.debug(f"[redis_state] Failed to set value in Redis: {e}")
            pass

    def incr_sync(self, key: str, ex: Optional[int] = None) -> int:
        """Increment a counter in the state store (Postgres or memory) with optional expiration."""
        r = self._get_redis_sync()
        if r is None:
            if self._pg_available():
                if ex:
                    row = self._pg_exec_one(
                        "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                        "VALUES (%s, jsonb_build_object('value', 1), NOW() + (%s || ' seconds')::interval, NOW()) "
                        "ON CONFLICT (key) DO UPDATE SET "
                        "value = jsonb_build_object('value', "
                        "CASE WHEN runtime_state.expires_at IS NOT NULL AND runtime_state.expires_at > NOW() "
                        "THEN COALESCE((runtime_state.value->>'value')::int, 0) + 1 ELSE 1 END), "
                        "expires_at = EXCLUDED.expires_at, updated_at = NOW() "
                        "RETURNING (value->>'value')::int",
                        (key, str(ex)),
                    )
                else:
                    row = self._pg_exec_one(
                        "INSERT INTO runtime_state(key, value, expires_at, updated_at) "
                        "VALUES (%s, jsonb_build_object('value', 1), NULL, NOW()) "
                        "ON CONFLICT (key) DO UPDATE SET "
                        "value = jsonb_build_object('value', COALESCE((runtime_state.value->>'value')::int, 0) + 1), "
                        "updated_at = NOW() "
                        "RETURNING (value->>'value')::int",
                        (key,),
                    )
                return int((row or (0,))[0] or 0)
            # Memory fallback
            current = int(self._memory.get(key, 0))
            current += 1
            self._memory[key] = current
            return current
        # Redis path (not used in this project)
        try:
            count = int(r.incr(key))
            if ex and count == 1:
                r.expire(key, ex)
            return count
        except Exception as e:
            import logging
            logging.debug(f"[redis_state] Failed to increment counter in Redis: {e}")
            return 0

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
