"""Shared httpx AsyncClient and lightweight retry/circuit helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

try:
    import httpx
except Exception:  # pragma: no cover - optional dependency
    httpx = None

logger = logging.getLogger(__name__)

_CLIENT: Optional["httpx.AsyncClient"] = None


def get_client() -> Optional["httpx.AsyncClient"]:
    global _CLIENT
    if httpx is None:
        return None
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(timeout=10.0)
    return _CLIENT


async def close_client():
    global _CLIENT
    if _CLIENT is not None:
        try:
            await _CLIENT.aclose()
        except Exception:
            logger.exception("failed to close httpx client")
        _CLIENT = None


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
