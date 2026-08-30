"""Glassnode adapter (advanced on-chain metrics).

Role (provider addendum §20): exchange flows, active addresses, realized cap,
MVRV-like metrics, network fees.  API access is a paid add-on; the adapter
stays dormant until ``GLASSNODE_API_KEY`` is configured.

This adapter supersedes the context-only fetcher in
``data.alternative_providers.fetch_glassnode_context`` (kept for backwards
compatibility) by providing the full normalized request surface.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.glassnode.com/v1"


def _enabled() -> bool:
    return env_bool("GLASSNODE_ENABLED", False)


def _api_key() -> str:
    return env_str("GLASSNODE_API_KEY")


async def _async_onchain_metric(asset: str, metric: str) -> Optional[Dict[str, Any]]:
    """Fetch one on-chain metric series point (latest)."""
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{API_URL}/metrics/{metric}",
        name="glassnode",
        params={"a": str(asset).upper(), "api_key": _api_key(), "i": "24h", "timestamp_format": "unix"},
        timeout=10.0,
    )
    if not isinstance(data, list) or not data:
        return None
    return {"asset": str(asset).upper(), "metric": metric, **data[-1]}


def onchain_metric(asset: str, metric: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_onchain_metric(asset, metric))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "glassnode",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("GLASSNODE_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "health", "onchain_metric"]
