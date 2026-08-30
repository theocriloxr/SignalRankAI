"""CryptoQuant adapter (exchange flows, miner data, institutional on-chain).

Role (provider addendum §20): exchange flows, stablecoin metrics, network
activity.  The free plan is low-resolution; higher plans provide better
history and API limits.  Dormant until ``CRYPTOQUANT_API_KEY`` is configured.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.cryptoquant.com/v1"


def _enabled() -> bool:
    return env_bool("CRYPTOQUANT_ENABLED", False)


def _api_key() -> str:
    return env_str("CRYPTOQUANT_API_KEY")


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def _async_onchain_metric(exchange: str, metric: str) -> Optional[Dict[str, Any]]:
    """Fetch the latest point of an on-chain metric for an exchange."""
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{API_URL}/metrics/exchange/{metric}",
        name="cryptoquant",
        params={"exchange": str(exchange).lower(), "window": "day", "limit": 1},
        headers=_headers(), timeout=10.0,
    )
    if not isinstance(data, dict):
        return None
    result = (data.get("result") or {}).get("data") or []
    if not result:
        return None
    return {"exchange": str(exchange).lower(), "metric": metric, **result[-1]}


def onchain_metric(exchange: str, metric: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_onchain_metric(exchange, metric))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "cryptoquant",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("CRYPTOQUANT_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "health", "onchain_metric"]
