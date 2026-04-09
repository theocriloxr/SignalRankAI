"""Shared httpx AsyncClient and lightweight retry/circuit helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional
from utils import proxy_manager

try:
    import httpx
except Exception:  # pragma: no cover - optional dependency
    httpx = None

logger = logging.getLogger(__name__)

_CLIENTS: dict[str, "httpx.AsyncClient"] = {}


def get_client(provider: str | None = None) -> Optional["httpx.AsyncClient"]:
    global _CLIENTS
    if httpx is None:
        return None
    proxy_url = proxy_manager.next_proxy_url_sync()
    key = f"{provider or '__default__'}|{proxy_url or '__direct__'}"
    client = _CLIENTS.get(key)
    if client is not None:
        return client
    kwargs: dict[str, Any] = {"timeout": 10.0}
    if proxy_url:
        kwargs["proxy"] = proxy_url
    _CLIENTS[key] = httpx.AsyncClient(**kwargs)
    return _CLIENTS[key]


async def close_client():
    global _CLIENTS
    for client in list(_CLIENTS.values()):
        try:
            await client.aclose()
        except Exception:
            logger.exception("failed to close httpx client")
    _CLIENTS = {}


async def retry_async(fn: Callable[..., Any], retries: int = 3, backoff: float = 1.0, *args, **kwargs) -> Any:
    last_exc = None
    for attempt in range(retries):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            wait = backoff * (2 ** attempt)
            await asyncio.sleep(wait)
    raise last_exc
