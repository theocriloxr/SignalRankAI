"""Shared helpers for provider adapters (env parsing + HTTP JSON fetch).

Kept deliberately small: adapters stay standalone and testable, and only reuse
the two operations every adapter needs.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Optional

from utils import httpx_client

logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool = False) -> bool:
    import os

    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_str(name: str, default: str = "") -> str:
    import os

    return str(os.getenv(name) or default).strip()


async def async_http_get_json(
    url: str,
    *,
    name: str,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = 8.0,
    retries: int = 2,
) -> Optional[Any]:
    """GET a JSON payload through the shared httpx client with bounded retries.

    Returns ``None`` on transport/HTTP failure (callers treat None as "no
    data"), never raises into the pipeline.
    """
    client = httpx_client.get_client(name)
    if client is None:
        logger.debug("%s: httpx client unavailable", name)
        return None

    async def _do():
        resp = await client.get(
            url, params=dict(params or {}), headers=dict(headers or {}), timeout=timeout
        )
        if resp.status_code != 200:
            logger.debug("%s HTTP %s url=%s", name, resp.status_code, url)
            return None
        return resp.json()

    try:
        return await asyncio.wait_for(
            httpx_client.retry_async(_do, retries=max(0, int(retries)), backoff=0.5),
            timeout=timeout + 1.0,
        )
    except Exception as exc:  # noqa: BLE001 - adapter boundary
        logger.debug("%s request error: %s", name, exc)
        return None


__all__ = ["async_http_get_json", "env_bool", "env_str"]
