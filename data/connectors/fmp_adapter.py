"""
FMP Adapter - Financial Modeling Prep (Stocks)

API Key required: FMP_API_KEY
Free Tier: 250 requests per day
Best for: Stocks, ETFs, Forex (NOT crypto)

Docs: https://site.financialmodelingprep.com/developer/docs
"""
from __future__ import annotations

from typing import List, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)

_LAST_CERTIFICATION_HINT: Dict[str, str] | None = None


def _set_certification_hint(status: str | None, reason: str = "") -> None:
    global _LAST_CERTIFICATION_HINT
    _LAST_CERTIFICATION_HINT = (
        {"status": str(status), "reason": str(reason)[:500]}
        if status else None
    )


def _classify_external_block(status_code: int, detail: str) -> tuple[str | None, str]:
    text = str(detail or "").strip().replace("\n", " ")[:500]
    lowered = text.lower()
    if status_code == 429 or "rate limit" in lowered or "too many requests" in lowered:
        return "BLOCKED_RATE_LIMIT", text or f"HTTP {status_code}"
    if any(token in lowered for token in ("premium", "subscription", "upgrade your plan", "paid plan")):
        return "BLOCKED_PAID_PLAN", text or f"HTTP {status_code}"
    if status_code in {401, 403} or any(
        token in lowered for token in ("invalid api key", "invalid apikey", "not authorized", "unauthorized")
    ):
        return "BLOCKED_ACCOUNT_APPROVAL", text or f"HTTP {status_code}"
    if any(token in lowered for token in ("region", "country", "not available in your location")):
        return "BLOCKED_REGION", text or f"HTTP {status_code}"
    return None, text


def certification_hint() -> Dict[str, str] | None:
    return dict(_LAST_CERTIFICATION_HINT) if _LAST_CERTIFICATION_HINT else None


try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils import httpx_client


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """Fetch normalized candles from FMP's current stable chart endpoints."""
    _set_certification_hint(None)
    api_key = (os.getenv("FMP_API_KEY") or "").strip()
    if not api_key or httpx is None:
        return []
    symbol_clean = (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    tf = (timeframe or "1h").strip().lower()
    interval_map = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1hour", "4h": "4hour"}
    if tf in {"1d", "d", "day", "daily"}:
        url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    else:
        interval = interval_map.get(tf)
        if not interval:
            return []
        url = f"https://financialmodelingprep.com/stable/historical-chart/{interval}"
    params = {"symbol": symbol_clean, "apikey": api_key}
    client = httpx_client.get_client("fmp")
    request_timeout = min(12.0, max(2.0, float(timeout)))
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=request_timeout) as fallback:
                response = await fallback.get(url, params=params)
        else:
            response = await client.get(url, params=params, timeout=request_timeout)
        if response.status_code != 200:
            detail = getattr(response, "text", "")[:500]
            status, reason = _classify_external_block(int(response.status_code), detail)
            _set_certification_hint(status, reason)
            logger.debug("fmp_adapter HTTP %s: %s", response.status_code, detail[:200])
            return []
        payload = response.json()
        if isinstance(payload, dict):
            rows = payload.get("historical") or payload.get("data") or []
            if not rows:
                detail = str(
                    payload.get("Error Message")
                    or payload.get("error")
                    or payload.get("message")
                    or payload.get("Information")
                    or ""
                )
                status, reason = _classify_external_block(int(response.status_code), detail)
                _set_certification_hint(status, reason)
        else:
            rows = payload or []
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows[: max(1, int(limit or 200))]:
            if not isinstance(row, dict):
                continue
            try:
                out.append({
                    "timestamp": row.get("date") or row.get("datetime") or row.get("timestamp"),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0) or 0),
                })
            except (TypeError, ValueError):
                continue
        return list(reversed(out))
    except Exception as exc:
        logger.debug("fmp_adapter exception: %s", exc)
        return []


async def _async_get_quote(
    symbol: str,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """
    Fetch real-time quote from FMP.
    
    Args:
        symbol: Trading symbol (e.g., "AAPL")
        timeout: Request timeout
        
    Returns:
        Dict with keys: price, change, changePercent, volume
    """
    api_key = (os.getenv("FMP_API_KEY") or "").strip()
    if not api_key:
        return {}

    symbol = (symbol or "").upper().strip()
    
    request_timeout = min(5.0, max(1.0, float(timeout)))
    
    try:
        url = "https://financialmodelingprep.com/stable/quote"
        
        client = httpx_client.get_client("fmp")
        
        if client is not None:
            resp = await client.get(url, params={"symbol": symbol, "apikey": api_key}, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url, params={"symbol": symbol, "apikey": api_key})
        
        if resp.status_code != 200:
            return {}
        
        data = resp.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return {}
        
        quote = data[0]
        
        return {
            "price": float(quote.get("price", 0)),
            "change": float(quote.get("change", 0)),
            "changePercent": float(quote.get("changesPercentage", 0)),
            "volume": float(quote.get("volume", 0)),
            "dayHigh": float(quote.get("dayHigh", 0)),
            "dayLow": float(quote.get("dayLow", 0)),
            "yearHigh": float(quote.get("yearHigh", 0)),
            "yearLow": float(quote.get("yearLow", 0)),
        }
        
    except Exception as e:
        logger.debug(f"fmp_adapter quote error: {e}")
        return {}


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async FMP client safely.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
