from __future__ import annotations

import os
import threading
from typing import Optional


_LOCK = threading.Lock()
_INDEX = 0


def _load_proxies() -> list[str]:
    raw = (os.getenv("PROXY_LIST") or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        p = str(part or "").strip()
        if p:
            out.append(p)
    return out


def _next_proxy() -> Optional[str]:
    global _INDEX
    proxies = _load_proxies()
    if not proxies:
        return None
    with _LOCK:
        idx = _INDEX % len(proxies)
        _INDEX = (_INDEX + 1) % len(proxies)
        return proxies[idx]


async def next_proxy_url() -> Optional[str]:
    """Async round-robin proxy selector from PROXY_LIST."""
    return _next_proxy()


def next_proxy_url_sync() -> Optional[str]:
    """Sync round-robin proxy selector from PROXY_LIST."""
    return _next_proxy()


def ccxt_proxy_config_sync() -> dict:
    """Return ccxt-compatible proxy config using round-robin URL."""
    proxy = next_proxy_url_sync()
    if not proxy:
        return {}
    return {"proxies": {"http": proxy, "https": proxy}}

