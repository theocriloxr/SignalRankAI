"""DefiLlama free endpoint adapter (context + on-chain discovery, keyless).

Roles (provider addendum §20):
* TVL, stablecoin totals, protocol yields, token unlock context
* DEX/on-chain instrument discovery metadata
* NEVER used for execution quotes or final delivery prices.

All endpoints are public and keyless; ``DEFILLAMA_PRO_ENABLED`` gates the paid
(``api.llama.fi`` premium) surface when the deployment actually subscribes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from data.connectors._common import async_http_get_json, env_bool
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

PUBLIC_API_URL = "https://api.llama.fi"
STABLECOINS_API_URL = "https://stablecoins.llama.fi"
YIELDS_API_URL = "https://yields.llama.fi"


def _enabled() -> bool:
    return env_bool("DEFILLAMA_ENABLED", True)


async def _async_stablecoin_totals() -> Optional[Dict[str, Any]]:
    if not _enabled():
        return None
    data = await async_http_get_json(
        f"{STABLECOINS_API_URL}/stablecoincharts/all", name="defillama", timeout=8.0
    )
    if not isinstance(data, list) or not data:
        return None
    return {"source": "stablecoins.llama.fi", "points": len(data), "latest_total_usd": data[-1].get("totalCirculatingUSD")}


def get_stablecoin_totals() -> Optional[Dict[str, Any]]:
    return run_sync(_async_stablecoin_totals())


async def _async_protocols_tvl() -> Optional[List[Dict[str, Any]]]:
    """Protocol TVL snapshot (metadata/context only)."""
    if not _enabled():
        return None
    data = await async_http_get_json(f"{PUBLIC_API_URL}/protocols", name="defillama", timeout=10.0)
    if not isinstance(data, list):
        return None
    return [
        {
            "protocol": str(item.get("name") or "")[:64],
            "chain": str(item.get("chain") or ""),
            "tvl_usd": item.get("tvl"),
            "tokens": [str(t or "")[:16] for t in (item.get("tokens") or [])[:8]],
        }
        for item in data[:500]
        if item.get("name")
    ]


def get_protocols_tvl() -> Optional[List[Dict[str, Any]]]:
    return run_sync(_async_protocols_tvl())


async def _async_discover_instruments(*, top: int = 200) -> List[Dict[str, Any]]:
    """Discovery: stablecoin tokens + yield pools as on-chain instruments."""
    if not _enabled():
        return []
    out: List[Dict[str, Any]] = []
    coins = await async_http_get_json(
        f"{STABLECOINS_API_URL}/stablecoins", name="defillama",
        params={"includePrices": "false"}, timeout=10.0,
    )
    if isinstance(coins, dict):
        for item in (coins.get("peggedAssets") or [])[: max(1, top)]:
            try:
                symbol = str(item.get("symbol") or "").upper().strip()
                if not symbol:
                    continue
                out.append({
                    "provider": "defillama",
                    "venue": "defillama",
                    "provider_symbol": f"{symbol}USDT",
                    "asset_class": "crypto",
                    "instrument_type": "spot",
                    "base": symbol,
                    "quote": "USDT",
                    "market_status": "active",
                    "metadata": {
                        "pegged_to": item.get("pegType"),
                        "chains": item.get("chains"),
                        "source": "stablecoins",
                    },
                })
            except Exception:
                continue
    return out


def discover_instruments(*, top: int = 200) -> List[Dict[str, Any]]:
    return run_sync(_async_discover_instruments(top=top))


def health() -> Dict[str, Any]:
    return {
        "provider_id": "defillama",
        "enabled": _enabled(),
        "pro_enabled": env_bool("DEFILLAMA_PRO_ENABLED", False),
        "state": "disabled" if not _enabled() else "public_ready",
        "api_url": PUBLIC_API_URL,
    }


__all__ = ["discover_instruments", "get_protocols_tvl", "get_stablecoin_totals", "health"]
