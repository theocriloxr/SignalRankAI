"""
Tiingo Adapter - Premium Free Tier Provider

API Key required: TIINGO_API_KEY
Free Tier: 500 requests per hour
Best for: Stocks, Crypto, Forex

Docs: https://api.tiingo.com/docs/tiingo
"""
from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import math
import os
import logging

logger = logging.getLogger(__name__)

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils import httpx_client


# Known crypto bases for detection
CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT",
    "LINK", "MATIC", "FIL", "APT", "NEAR", "ALGO", "ATOM", "UNI", "LTC",
    "BCH", "ETC", "XLM", "VET", "HBAR", "ALGB", "FTM", "SAND", "MANA",
}
FIAT_CODES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SGD", "HKD"}


def _split_pair(symbol: str) -> tuple[str, str]:
    value = str(symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    for quote in ("USDT", "USDC", "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SGD", "HKD"):
        if value.endswith(quote) and len(value) > len(quote):
            return value[:-len(quote)], quote
    return value, ""


def _lookback_start(timeframe: str, limit: int) -> str:
    tf_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }.get(str(timeframe or "").lower(), 60)
    requested = max(2, int(limit or 200))
    trading_days = max(14, int(math.ceil((requested * tf_minutes) / 1440.0)) + 7)
    return (datetime.now(timezone.utc) - timedelta(days=min(3650, trading_days))).date().isoformat()


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Fetch candles from Tiingo API.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "AAPL")
        timeframe: Timeframe (1h, 4h, 1d) 
        limit: Number of candles to fetch
        timeout: Request timeout
        
    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close, volume
    """
    api_key = (os.getenv("TIINGO_API_KEY") or "").strip()
    if not api_key:
        logger.debug("tiingo_adapter: TIINGO_API_KEY not set")
        return []

    symbol = (symbol or "").upper().strip()
    symbol_clean = symbol.replace("/", "").replace("-", "").replace("_", "")
    base, quote = _split_pair(symbol_clean)
    is_crypto = base in CRYPTO_BASES and quote in {"USD", "USDT", "USDC"}
    is_forex = base in FIAT_CODES and quote in FIAT_CODES
    requested = max(2, int(limit or 200))

    tf_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1hour",
        "4h": "4hour",
        "1d": "1day",
    }
    tf = (timeframe or "").strip().lower()
    resample_tf = tf_map.get(tf, "1hour")
    start_date = _lookback_start(tf, requested)
    request_timeout = min(10.0, max(2.0, float(timeout)))

    try:
        if is_crypto:
            tiingo_symbol = f"{base.lower()}usd"
            url = "https://api.tiingo.com/tiingo/crypto/prices"
            params = {
                "tickers": tiingo_symbol,
                "resampleFreq": resample_tf,
                "startDate": start_date,
                "token": api_key,
            }
        elif is_forex:
            url = f"https://api.tiingo.com/tiingo/fx/{symbol_clean.lower()}/prices"
            params = {
                "resampleFreq": resample_tf,
                "startDate": start_date,
                "token": api_key,
            }
        elif tf == "1d":
            url = f"https://api.tiingo.com/tiingo/daily/{symbol_clean.lower()}/prices"
            params = {"startDate": start_date, "token": api_key}
        else:
            url = f"https://api.tiingo.com/iex/{symbol_clean.lower()}/prices"
            params = {
                "resampleFreq": resample_tf,
                "startDate": start_date,
                "token": api_key,
            }

        client = httpx_client.get_client("tiingo")

        if client is not None:
            resp = await client.get(url, params=params, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url, params=params)
        
        if resp.status_code != 200:
            logger.debug(f"tiingo_adapter HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}")
            return []
        
        data = resp.json()
        
        if not data or not isinstance(data, list):
            return []
        
        out: List[Dict[str, Any]] = []
        
        if is_crypto:
            # Crypto returns: [{"ticker": "...", "priceData": [...]}]
            price_data = data[0].get("priceData", []) if data else []
            for row in price_data[-requested:]:
                try:
                    # Row format per Tiingo docs
                    out.append({
                        "timestamp": row.get("date"),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                    })
                except (ValueError, TypeError) as e:
                    logger.debug(f"tiingo_adapter parse error: {e}")
                    continue
        else:
            # Stocks/Forex returns: [{date, open, high, low, close, volume}, ...]
            for row in data[-requested:]:
                try:
                    out.append({
                        "timestamp": row.get("date"),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                    })
                except (ValueError, TypeError) as e:
                    logger.debug(f"tiingo_adapter parse error: {e}")
                    continue
        
        out.sort(key=lambda item: str(item.get("timestamp") or ""))
        return out[-requested:]
        
    except Exception as e:
        logger.debug(f"tiingo_adapter exception: {e}")
        return []


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async Tiingo client safely.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
