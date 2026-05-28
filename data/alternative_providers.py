from __future__ import annotations

import os
from typing import Any, Dict

import httpx


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _numeric_from_payload(payload: Any, *keys: str, default: float = 0.0) -> float:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            try:
                if value is not None:
                    return float(value)
            except Exception:
                continue
        # Nested common shapes
        for nested_key in ("data", "result", "items"):
            if nested_key in payload:
                value = _numeric_from_payload(payload.get(nested_key), *keys, default=default)
                if value != default:
                    return value
    if isinstance(payload, list) and payload:
        for item in payload:
            value = _numeric_from_payload(item, *keys, default=default)
            if value != default:
                return value
    return float(default)


async def _fetch_json(url: str, *, headers: Dict[str, str] | None = None, params: Dict[str, Any] | None = None, timeout: float = 3.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}


def _context_from_payload(payload: Dict[str, Any], source: str) -> Dict[str, float | str]:
    exchange_net_flow = _numeric_from_payload(payload, "exchange_net_flow", "exchangeNetFlow", "netflow", "net_flow", "net_flow_btc", default=0.0)
    liquidation_heatmap_score = _numeric_from_payload(payload, "liquidation_heatmap_score", "heatmap_score", "score", default=0.0)
    liquidation_heatmap_density = _numeric_from_payload(payload, "liquidation_heatmap_density", "heatmap_density", "density", default=0.0)
    exchange_inflow = _numeric_from_payload(payload, "exchange_inflow", "inflow", "exchangeInflow", default=0.0)
    exchange_outflow = _numeric_from_payload(payload, "exchange_outflow", "outflow", "exchangeOutflow", default=0.0)
    return {
        "onchain_source": source,
        "exchange_net_flow": float(exchange_net_flow if exchange_net_flow != 0.0 else exchange_inflow - exchange_outflow),
        "exchange_inflow": float(exchange_inflow),
        "exchange_outflow": float(exchange_outflow),
        "liquidation_heatmap_score": float(liquidation_heatmap_score),
        "liquidation_heatmap_density": float(liquidation_heatmap_density),
    }


async def fetch_glassnode_context(symbol: str) -> Dict[str, float | str]:
    if not _env_bool("GLASSNODE_ENABLED", True):
        return {"onchain_source": "glassnode", "exchange_net_flow": 0.0, "exchange_inflow": 0.0, "exchange_outflow": 0.0, "liquidation_heatmap_score": 0.0, "liquidation_heatmap_density": 0.0}
    endpoint = _env_str("GLASSNODE_ONCHAIN_ENDPOINT")
    if not endpoint:
        return {"onchain_source": "glassnode", "exchange_net_flow": 0.0, "exchange_inflow": 0.0, "exchange_outflow": 0.0, "liquidation_heatmap_score": 0.0, "liquidation_heatmap_density": 0.0}
    headers = {}
    api_key = _env_str("GLASSNODE_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key
    payload = await _fetch_json(endpoint, headers=headers or None, params={"symbol": symbol})
    return _context_from_payload(payload, "glassnode")


async def fetch_cryptoquant_context(symbol: str) -> Dict[str, float | str]:
    if not _env_bool("CRYPTOQUANT_ENABLED", True):
        return {"onchain_source": "cryptoquant", "exchange_net_flow": 0.0, "exchange_inflow": 0.0, "exchange_outflow": 0.0, "liquidation_heatmap_score": 0.0, "liquidation_heatmap_density": 0.0}
    endpoint = _env_str("CRYPTOQUANT_ONCHAIN_ENDPOINT")
    if not endpoint:
        return {"onchain_source": "cryptoquant", "exchange_net_flow": 0.0, "exchange_inflow": 0.0, "exchange_outflow": 0.0, "liquidation_heatmap_score": 0.0, "liquidation_heatmap_density": 0.0}
    headers = {}
    api_key = _env_str("CRYPTOQUANT_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key
    payload = await _fetch_json(endpoint, headers=headers or None, params={"symbol": symbol})
    return _context_from_payload(payload, "cryptoquant")


async def fetch_onchain_context(symbol: str) -> Dict[str, float | str]:
    """Fetch on-chain and liquidation context from configured providers.

    The integration is fail-open: if providers are disabled or endpoints are
    missing, a zero-filled context is returned.
    """
    result: Dict[str, float | str] = {
        "onchain_source": "none",
        "exchange_net_flow": 0.0,
        "exchange_inflow": 0.0,
        "exchange_outflow": 0.0,
        "liquidation_heatmap_score": 0.0,
        "liquidation_heatmap_density": 0.0,
    }
    for fetcher in (fetch_glassnode_context, fetch_cryptoquant_context):
        try:
            payload = await fetcher(symbol)
            if not payload:
                continue
            result.update(payload)
        except Exception:
            continue
    return result
