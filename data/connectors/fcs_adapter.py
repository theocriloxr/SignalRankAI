"""FCS v4 read-only candles; provider access is verified separately.

Contracts: https://fcsapi.com/document/forex-api and /stock-api, /crypto-api.
Credentials stay in the POST body and never enter logs or request URLs.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any

from core.asset_registry import resolve_asset_spec
from data.provider_catalog import evaluate_candle_freshness, validate_candles
from utils import httpx_client
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)
TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h", "5h", "1d", "1w"})
BASE_URL = "https://api-v4.fcsapi.com"


def _request_identity(symbol: str) -> tuple[str, str] | None:
    raw = str(symbol or "").strip().upper()
    spec = resolve_asset_spec(raw.split(":")[-1])
    market = {"forex": "forex", "commodity": "forex", "stock": "stock",
              "index": "stock", "crypto": "crypto"}.get(spec.asset_class)
    if market is None:
        return None
    # Preserve exchange prefixes and stock punctuation; never substitute an ETF.
    mapped = raw.replace("/", "").replace("_", "") if spec.asset_class == "forex" else raw
    configured = os.getenv("FCS_SYMBOL_MAP_JSON", "").strip()
    if configured:
        try:
            mapping = json.loads(configured)
            if not isinstance(mapping, dict):
                return None
            mapped = mapping.get(raw, mapped)
        except (ValueError, TypeError):
            return None
    if not isinstance(mapped, str) or not mapped.strip() or len(mapped) > 100:
        return None
    return market, mapped.strip()


async def _request(market: str, endpoint: str, params: dict[str, Any], timeout: float) -> Any:
    from data.providers import _is_cooldown_active, _maybe_apply_rate_limit_cooldown

    if _is_cooldown_active("fcs"):
        return None
    key = (os.getenv("FCS_API_KEY") or os.getenv("FCS_API_SECRET") or "").strip()
    client = httpx_client.get_client("fcs") if key else None
    if client is None:
        return None
    try:
        response = await client.post(f"{BASE_URL}/{market}/{endpoint}", json={**params, "access_key": key}, timeout=timeout)
        if response.status_code != 200:
            _maybe_apply_rate_limit_cooldown("fcs", status_code=response.status_code)
            logger.debug("fcs_adapter rejected http_status=%s", response.status_code)
            return None
        payload = response.json()
        if isinstance(payload, dict) and (payload.get("status") is False or payload.get("code") not in (None, 200, "200")):
            _maybe_apply_rate_limit_cooldown("fcs", message=str(payload.get("msg") or ""))
            logger.debug("fcs_adapter provider_rejected")
            return None
        return payload.get("response", payload) if isinstance(payload, dict) else payload
    except Exception as exc:
        logger.debug("fcs_adapter error_type=%s", type(exc).__name__)
        return None


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> list[dict[str, Any]]:
    identity = _request_identity(symbol)
    tf = str(timeframe or "").strip().lower()
    if identity is None or tf not in TIMEFRAMES:
        return []
    try:
        requested = max(1, min(1000, int(limit)))
        request_timeout = min(10.0, max(1.0, float(timeout)))
        if not math.isfinite(float(timeout)):
            return []
    except (ValueError, TypeError, OverflowError):
        return []
    market, ticker = identity
    payload = await _request(market, "history", {"symbol": ticker, "period": tf, "length": requested, "page": 1, "is_chart": 0}, request_timeout)
    if isinstance(payload, dict):
        bars = list(payload.values())
    elif isinstance(payload, list):
        bars = payload
    else:
        return []
    out = []
    for bar in bars:
        try:
            if isinstance(bar, list) and len(bar) >= 6:
                stamp, opened, high, low, close, volume = bar[:6]
            elif isinstance(bar, dict):
                stamp, opened, high, low, close, volume = (bar.get(field) for field in ("t", "o", "h", "l", "c", "v"))
            else:
                return []
            out.append({"timestamp": float(stamp), "open": float(opened), "high": float(high),
                        "low": float(low), "close": float(close), "volume": float(volume or 0)})
        except (ValueError, TypeError, OverflowError):
            return []
    out.sort(key=lambda bar: bar["timestamp"])
    if not validate_candles(out, minimum=1)["valid"]:
        return []
    return out[-requested:]


async def _async_get_latest_price(symbol: str, timeout: float = 5.0) -> float:
    """Analysis price only; execution consumes the timestamped quote contract."""
    identity = _request_identity(symbol)
    if identity is None:
        return 0.0
    market, ticker = identity
    payload = await _request(market, "latest", {"symbol": ticker}, min(5.0, max(1.0, timeout)))
    row = payload[0] if isinstance(payload, list) and payload else payload
    active = row.get("active") if isinstance(row, dict) else None
    if not isinstance(active, dict):
        return 0.0
    fresh = evaluate_candle_freshness({"last_timestamp": row.get("update") or active.get("t")}, interval_seconds=60, now_epoch=time.time())
    try:
        price = float(active.get("c"))
    except (ValueError, TypeError):
        return 0.0
    return price if fresh["fresh"] and math.isfinite(price) and price > 0 else 0.0


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> list[dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
