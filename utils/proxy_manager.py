from __future__ import annotations

import os
import threading
from typing import Optional

from sqlalchemy import select

from db.models import ProxyNode
from db.session import get_session
from utils.async_runner import run_sync

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None


_LOCK = threading.Lock()
_INDEX = 0
_PROXY_CACHE_RAW = ""
_PROXY_CACHE_LIST: list[str] = []
_REDIS_CLIENT = None
_REDIS_UNAVAILABLE = False
_PROXY_POOL_KEY = "proxy_pool:active"


def _redis_url() -> str:
    """Checks env vars in order: REDIS_URL, REDIS_PRIVATE_URL, REDIS_PUBLIC_URL, REDIS_INTERNAL_URL, REDIS_TLS_URL."""
    for key in ("REDIS_URL", "REDIS_PRIVATE_URL", "REDIS_PUBLIC_URL", "REDIS_INTERNAL_URL", "REDIS_TLS_URL"):
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    return ""


def _get_redis_sync():
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if _REDIS_UNAVAILABLE:
        return None
    if redis is None:
        return None
    url = _redis_url()
    if not url:
        return None
    try:
        _REDIS_CLIENT = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
            retry_on_timeout=True,
        )
        _REDIS_CLIENT.ping()
        return _REDIS_CLIENT
    except Exception:
        _REDIS_CLIENT = None
        _REDIS_UNAVAILABLE = True
        return None


def normalize_proxy_url(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw


def _parse_proxy_csv(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        n = normalize_proxy_url(part)
        if n:
            out.append(n)
    return out


def _next_proxy_from_env() -> Optional[str]:
    global _INDEX, _PROXY_CACHE_RAW, _PROXY_CACHE_LIST
    with _LOCK:
        raw = (os.getenv("PROXY_LIST") or "").strip()
        if raw != _PROXY_CACHE_RAW:
            _PROXY_CACHE_RAW = raw
            _PROXY_CACHE_LIST = _parse_proxy_csv(raw)
            _INDEX = 0
        proxies = _PROXY_CACHE_LIST
        if not proxies:
            return None
        idx = _INDEX % len(proxies)
        _INDEX = (_INDEX + 1) % len(proxies)
        return proxies[idx]


def _set_redis_pool_sync(proxy_urls: list[str]) -> None:
    client = _get_redis_sync()
    if client is None:
        return
    cleaned = []
    seen: set[str] = set()
    for p in proxy_urls:
        n = normalize_proxy_url(p)
        if not n or n in seen:
            continue
        seen.add(n)
        cleaned.append(n)
    try:
        pipe = client.pipeline()
        pipe.delete(_PROXY_POOL_KEY)
        if cleaned:
            pipe.rpush(_PROXY_POOL_KEY, *cleaned)
        pipe.execute()
    except Exception:
        return


def _rotate_redis_proxy_sync() -> Optional[str]:
    client = _get_redis_sync()
    if client is None:
        return None
    try:
        # Rotate in-place and return next proxy in O(1)
        value = client.rpoplpush(_PROXY_POOL_KEY, _PROXY_POOL_KEY)
        if not value:
            return None
        return normalize_proxy_url(str(value))
    except Exception:
        return None


async def _fetch_active_proxies_from_db() -> list[str]:
    async with get_session() as session:
        rows = await session.scalars(
            select(ProxyNode.proxy_url)
            .where(ProxyNode.is_active.is_(True))
            .order_by(ProxyNode.fail_count.asc(), ProxyNode.last_checked.desc())
        )
        urls = [str(v) for v in rows.all() if str(v or "").strip()]
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        n = normalize_proxy_url(raw)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def refresh_active_proxy_pool_sync() -> list[str]:
    try:
        active = run_sync(_fetch_active_proxies_from_db())
    except Exception:
        active = []
    if active:
        _set_redis_pool_sync(active)
    return active


async def refresh_active_proxy_pool() -> list[str]:
    active = await _fetch_active_proxies_from_db()
    _set_redis_pool_sync(active)
    return active


def get_proxy_sync() -> Optional[str]:
    proxy = _rotate_redis_proxy_sync()
    if proxy:
        return proxy
    active = refresh_active_proxy_pool_sync()
    if active:
        proxy = _rotate_redis_proxy_sync()
        if proxy:
            return proxy
        return active[0]
    return _next_proxy_from_env()


async def get_proxy() -> Optional[str]:
    return get_proxy_sync()


async def next_proxy_url() -> Optional[str]:
    return await get_proxy()


def next_proxy_url_sync() -> Optional[str]:
    return get_proxy_sync()


def ccxt_proxy_config_sync() -> dict:
    proxy = next_proxy_url_sync()
    if not proxy:
        return {}
    return {"proxies": {"http": proxy, "https": proxy}}
