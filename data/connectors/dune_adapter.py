"""Dune adapter (custom blockchain SQL analytics).

Role (provider addendum §20): scheduled queries and proprietary on-chain
datasets.  The official client is ``dune-client``; this adapter uses the HTTP
GraphQL/REST surface so no heavy SDK is required at import time.

Dormant-by-default: without ``DUNE_API_KEY`` returns ``None`` and reports
``missing_credentials``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.dune.com/api/v1"


def _enabled() -> bool:
    return env_bool("DUNE_ENABLED", False)


def _api_key() -> str:
    return env_str("DUNE_API_KEY")


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"X-Dune-API-Key": key} if key else {}


async def _async_query_result(query_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the latest result of a configured Dune query."""
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{API_URL}/query/{query_id}/results",
        name="dune", headers=_headers(), timeout=15.0,
    )
    if not isinstance(data, dict):
        return None
    return {
        "query_id": query_id,
        "execution_id": data.get("execution_id"),
        "state": data.get("state"),
        "rows": (data.get("result") or {}).get("rows") if isinstance(data.get("result"), dict) else [],
    }


def query_result(query_id: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_query_result(query_id))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "dune",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("DUNE_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "health", "query_result"]
