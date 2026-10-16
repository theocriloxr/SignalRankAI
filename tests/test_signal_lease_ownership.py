"""State/ownership contracts, also run against an owned redis-server process.

The default command double is not a Redis integration certificate. The
certify_signal_leases script runs these contracts against actual Redis Lua.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
import uuid
from urllib.parse import urlparse

import pytest

from core.redis_state import RedisState
import core.redis_state as redis_state
from engine import signal_lock as locks


class AtomicRedisDouble:
    def __init__(self):
        self.values = {}
        self.guard = threading.Lock()

    def _get(self, key):
        value, expiry = self.values.get(key, (None, 0))
        return value if expiry > time.monotonic() else None

    def exists(self, *keys):
        with self.guard:
            return sum(self._get(key) is not None for key in keys)

    def get(self, key):
        with self.guard:
            return self._get(key)

    def set(self, key, value, *, ex):
        with self.guard:
            self.values[key] = value, time.monotonic() + ex
            return True

    def pexpire(self, key, milliseconds):
        with self.guard:
            self.values[key] = self._get(key), time.monotonic() + milliseconds / 1000

    def eval(self, script, key_count, *args):
        with self.guard:
            keys, params = args[:key_count], args[key_count:]
            if script.startswith("for i = 1"):
                if any(self._get(key) is not None for key in keys):
                    return 0
                token, ttl = params
                self.values[keys[0]] = token, time.monotonic() + ttl
                return 1
            if self._get(keys[0]) == params[0]:
                self.values.pop(keys[0], None)
                return 1
            return 0


@pytest.fixture
def lease_state(monkeypatch):
    instance = RedisState()
    test_url = os.getenv("SIGNALRANK_LEASE_TEST_REDIS_URL")
    if test_url:
        parsed = urlparse(test_url)
        assert parsed.hostname == "127.0.0.1" and parsed.port not in {None, 6379}
        assert parsed.username is None and parsed.password is None and parsed.path == "/0"
        import redis
        client = redis.from_url(test_url, decode_responses=True, socket_timeout=1)
        assert client.ping()
    else:
        client = AtomicRedisDouble()
    monkeypatch.setattr(instance, "_get_redis_sync", lambda: client)
    monkeypatch.setattr(redis_state, "state", instance)
    monkeypatch.setattr(locks, "_owned", locks.ContextVar("test_owned_leases", default=None))
    asset = "SRTEST" + uuid.uuid4().hex.upper()
    yield instance, client, asset
    if test_url:
        keys = list(client.scan_iter(match=f"signal_lock:{asset}:*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_authoritative_read_ignores_local_cache(lease_state):
    state, client, asset = lease_state
    key = locks._make_lock_key(asset, "buy", "1H")
    state._cache_set(key, "stale-local-cache", ex=100)
    assert locks.check_signal_lock(asset, "long", "1h") is False
    assert locks.acquire_signal_lock_sync(asset, "BUY", "1h")
    assert locks.check_signal_lock(asset, "long", "1H")
    assert client.get(key) != "stale-local-cache"
    assert locks.release_signal_lock_sync(asset, "long", "1h")
    assert not locks.check_signal_lock(asset, "buy", "1h")


@pytest.mark.parametrize("direction,timeframe", [("BUY", "1H"), ("LONG", "1H"), ("buy", "1h")])
def test_legacy_lock_is_respected(lease_state, direction, timeframe):
    _, client, asset = lease_state
    client.set(f"signal_lock:{asset}:{direction}:{timeframe}", "legacy-token", ex=30)
    assert locks.check_signal_lock(asset, "long", "1h")
    assert not locks.acquire_signal_lock_sync(asset, "long", "1h")
    assert not locks.release_signal_lock_sync(asset, "long", "1h")


def test_sides_are_independent(lease_state):
    _, _, asset = lease_state
    assert locks.acquire_signal_lock_sync(asset, "BUY", "1h")
    assert locks.acquire_signal_lock_sync(asset, "SELL", "1h")
    assert not locks.acquire_signal_lock_sync(asset, "long", "1h")
    assert locks.release_signal_lock_sync(asset, "short", "1h")
    assert locks.release_signal_lock_sync(asset, "long", "1h")


def test_thread_contention_has_one_winner(lease_state):
    _, client, asset = lease_state
    barrier = threading.Barrier(16)
    def contender():
        barrier.wait(timeout=5)
        acquired = locks.acquire_signal_lock_sync(asset, "long", "1h")
        return acquired, False if acquired else locks.release_signal_lock_sync(asset, "long", "1h")
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(lambda _: contender(), range(16)))
    assert sum(acquired for acquired, _ in results) == 1
    assert not any(released for _, released in results)
    assert client.exists(locks._make_lock_key(asset, "long", "1h")) == 1
    assert not locks.release_signal_lock_sync(asset, "long", "1h")


def test_async_contention_retains_task_owner(lease_state):
    _, _, asset = lease_state
    async def exercise():
        ready, finish = asyncio.Event(), asyncio.Event()
        async def winner():
            assert await locks.acquire_signal_lock(asset, "long", "1h")
            ready.set()
            await finish.wait()
            assert await locks.release_signal_lock(asset, "BUY", "1H")
        task = asyncio.create_task(winner())
        await ready.wait()
        assert not await locks.acquire_signal_lock(asset, "BUY", "1h")
        assert not await locks.release_signal_lock(asset, "long", "1h")
        assert await locks.is_signal_locked(asset, "long", "1h")
        finish.set()
        await task
        assert not await locks.is_signal_locked(asset, "long", "1h")
    asyncio.run(exercise())


def test_child_task_cannot_release_inherited_token(lease_state):
    _, _, asset = lease_state
    async def exercise():
        assert await locks.acquire_signal_lock(asset, "long", "1h")
        assert not await asyncio.create_task(locks.release_signal_lock(asset, "long", "1h"))
        assert locks.check_signal_lock(asset, "long", "1h")
        assert await locks.release_signal_lock(asset, "long", "1h")
    asyncio.run(exercise())


def test_expired_owner_cannot_delete_replacement(lease_state):
    state, client, asset = lease_state
    key = locks._make_lock_key(asset, "long", "1h")
    assert locks.acquire_signal_lock_sync(asset, "long", "1h", ttl_seconds=1)
    original = client.get(key)
    client.pexpire(key, 1)
    deadline = time.monotonic() + 2
    while client.exists(key) and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not client.exists(key)
    replacement = state.lease_acquire_sync(key, 30)
    assert replacement and replacement != original
    assert not locks.release_signal_lock_sync(asset, "long", "1h")
    assert client.get(key) == replacement
    assert state.lease_release_sync(key, replacement)


@pytest.mark.parametrize("ttl", [0, -1, True, 1.5, "5"])
def test_invalid_ttl_denies_acquisition(lease_state, ttl):
    _, _, asset = lease_state
    assert not locks.acquire_signal_lock_sync(asset, "long", "1h", ttl_seconds=ttl)


@pytest.mark.parametrize("asset,side,tf,group", [("", "long", "1h", None), ("BTC:USDT", "long", "1h", None),
    ("BTCUSDT", "sideways", "1h", None), ("BTCUSDT", "long", "1h:other", None),
    ("BTCUSDT", "long", "0h", None), ("BTCUSDT", "long", "1h", "group:other")])
def test_invalid_scope_fails_closed(lease_state, asset, side, tf, group):
    assert locks.check_signal_lock(asset, side, tf, group)
    assert not locks.acquire_signal_lock_sync(asset, side, tf, group)
    assert not locks.release_signal_lock_sync(asset, side, tf, group)


@pytest.mark.parametrize("mode", ["absent", "error"])
def test_redis_failure_has_no_memory_fallback(lease_state, monkeypatch, mode, caplog):
    state, _, asset = lease_state
    def unavailable():
        if mode == "error":
            raise RuntimeError("redis://secret-user:secret-password@private-host")
        return None
    monkeypatch.setattr(state, "_get_redis_sync", unavailable)
    assert locks.check_signal_lock(asset, "long", "1h")
    assert not locks.acquire_signal_lock_sync(asset, "long", "1h")
    assert not locks.release_signal_lock_sync(asset, "long", "1h")
    assert "secret-password" not in caplog.text


@pytest.mark.parametrize("method", ["exists", "eval"])
def test_command_failure_denies_generation(lease_state, monkeypatch, method):
    _, client, asset = lease_state
    def fail(*args, **kwargs):
        raise TimeoutError("uncertain Redis response")
    monkeypatch.setattr(client, method, fail)
    if method == "exists":
        assert locks.check_signal_lock(asset, "long", "1h")
    else:
        assert not locks.acquire_signal_lock_sync(asset, "long", "1h")


def test_telegram_and_database_share_lease(lease_state):
    _, _, asset = lease_state
    from signalrank_telegram.delivery_cooldown import set_signal_lock, clear_signal_lock, check_signal_lock
    from db.pg_features import acquire_signal_lock, release_signal_lock
    assert set_signal_lock(asset, "BUY", "1H")
    assert check_signal_lock(asset, "long", "1h")
    assert not asyncio.run(acquire_signal_lock(asset, "long", "1h"))
    asyncio.run(release_signal_lock(asset, "long", "1h"))
    assert check_signal_lock(asset, "long", "1h")
    assert clear_signal_lock(asset, "long", "1h")


def test_database_pair_retains_async_owner(lease_state):
    _, _, asset = lease_state
    from db.pg_features import acquire_signal_lock, release_signal_lock
    async def exercise():
        assert await acquire_signal_lock(asset, "BUY", "1H")
        await release_signal_lock(asset, "long", "1h")
        assert not await locks.is_signal_locked(asset, "long", "1h")
    asyncio.run(exercise())


def test_engine_wrapper_blocks_failed_acquisition(lease_state, monkeypatch):
    state, _, asset = lease_state
    from engine.core import _check_signal_lock, _release_signal_lock
    assert _check_signal_lock(asset, "BUY", "1H") is False
    assert _check_signal_lock(asset, "long", "1h") is True
    _release_signal_lock(asset, "long", "1h")
    monkeypatch.setattr(state, "_get_redis_sync", lambda: None)
    assert _check_signal_lock(asset, "long", "1h") is True


def test_active_signal_check_denies_database_failure():
    from signalrank_telegram.delivery_cooldown import check_active_signal_exists
    from db.pg_features import check_active_signal_exists as db_check
    class BrokenSession:
        async def execute(self, statement):
            raise ConnectionError("database unavailable")
    assert asyncio.run(check_active_signal_exists(BrokenSession(), "BTCUSDT", "long", "1h"))
    assert asyncio.run(db_check(BrokenSession(), "BTCUSDT", "long", "1h"))


def test_dedup_wrapper_awaits_actual_api_inside_running_loop(lease_state, monkeypatch):
    _, _, asset = lease_state
    from engine import dedup_wrapper as wrapper
    calls = []
    async def no_active(*args):
        return False
    class Deduplicator:
        async def is_duplicate(self, symbol, timeframe, side, entry):
            calls.append((symbol, timeframe, side, entry))
            return True
    monkeypatch.setattr(wrapper, "active_signal_exists_for_asset", no_active)
    monkeypatch.setattr(wrapper, "_dedup", Deduplicator())
    async def exercise():
        assert wrapper.should_skip_signal(asset, "BUY", "1H", signal_data={"entry": 100}) == (True, "memory_duplicate")
    asyncio.run(exercise())
    assert calls == [(asset, "1h", "long", 100)]


def test_dedup_memory_mark_cannot_override_failed_lease(lease_state, monkeypatch):
    _, _, asset = lease_state
    from engine import dedup_wrapper as wrapper
    monkeypatch.setattr(wrapper, "acquire_signal_lock_sync", lambda *args: False)
    class Deduplicator:
        async def register_signal(self, *args):
            pytest.fail("memory tracking cannot turn failed distributed acquisition into success")
    monkeypatch.setattr(wrapper, "_dedup", Deduplicator())
    assert wrapper.mark_signal_generated(asset, "long", "1h", signal_data={"entry": 100}) is False


def test_missing_dedup_authority_denies_generation(lease_state, monkeypatch):
    _, _, asset = lease_state
    from engine import dedup_wrapper as wrapper
    monkeypatch.setattr(wrapper, "active_signal_exists_for_asset", None)
    assert wrapper.should_skip_signal(asset, "long", "1h") == (True, "dedup_authority_unavailable")
