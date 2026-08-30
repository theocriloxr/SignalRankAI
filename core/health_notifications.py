"""Distributed idempotency claims for operational health notifications."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any

_LOCAL: dict[str, float] = {}
_LOCK = threading.Lock()


def claim_health_notification(
    event_type: str,
    evidence: Any,
    *,
    ttl_seconds: int = 300,
    deployment_scoped: bool = False,
) -> tuple[bool, str]:
    canonical = json.dumps(evidence, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
    deployment = str(os.getenv("RAILWAY_DEPLOYMENT_ID") or "local") if deployment_scoped else "global"
    key = f"signalrank:health-notification:{deployment}:{event_type}:{digest}"
    ttl = max(30, int(ttl_seconds))
    try:
        from core.redis_state import state

        client = state._get_redis_sync()
        if client is not None:
            return bool(client.set(key, str(time.time()), ex=ttl, nx=True)), key
    except Exception:
        pass
    now = time.monotonic()
    with _LOCK:
        expired = [name for name, expires in _LOCAL.items() if expires <= now]
        for name in expired:
            _LOCAL.pop(name, None)
        if key in _LOCAL:
            return False, key
        _LOCAL[key] = now + ttl
    return True, key
