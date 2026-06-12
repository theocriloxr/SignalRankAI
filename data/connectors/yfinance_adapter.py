from __future__ import annotations

from typing import List, Dict, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None

from utils.async_runner import run_sync

# Import the dynamic symbol formatter - this is the FIX for symbol mismatch silent failures
from data.symbol_formatter import format_symbol_for_yahoo, normalize_crypto_symbol


def _normalize_symbol(symbol: str) -> str:
    """
    Unified mapping to Yahoo-compatible symbols.
    
    FIX: Use dynamic symbol_formatter to fix "BTCUSDT -> BTC-USD" conversion.
    This fixes the silent failure where yfinance returns 0 candles due to symbol mismatch.
    """
    # Use the dynamic formatter - handles all edge cases
    try:
        formatted = format_symbol_for_yahoo(symbol)
        if formatted and formatted != symbol:
            logger.debug(f"[yfinance] symbol converted: {symbol} -> {formatted}")
        return formatted
    except Exception as e:
        # Fallback to simple normalization if dynamic formatter fails
        pass
    
    # Fallback implementation
    s = (symbol or "").upper().strip().replace("/", "").replace("_", "")
    if not s:
        return s

    overrides = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "WTI": "CL=F",
        "WTIUSD": "CL=F",
        "CRUDEOIL": "CL=F",
        "NATGAS": "NG=F",
    }
    if s in overrides:
        return overrides[s]

    # FX majors/crosses: EURUSD -> EURUSD=X
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        return f"{s}=X"

# Crypto pairs: BTCUSDT -> BTC-USD, BTCUSD -> BTC-USD
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}-USD"
    if s.endswith("USD") and len(s) > 3:
        base = s[:-3]
        crypto_bases = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "MATIC", "FIL", "APT", "NEAR", "ALGO"}
        if base in crypto_bases:
            return f"{base}-USD"

    return s


def _sync_get_candles_impl(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Original synchronous implementation kept as helper for thread execution."""
    if yf is None:
        raise RuntimeError("yfinance not installed")

    symbol_norm = _normalize_symbol(symbol)
    interval = timeframe
    period = "60d" if "d" in timeframe or "h" in timeframe else "7d"

    try:
        t = yf.Ticker(symbol_norm)
        df = t.history(period=period, interval=interval)
        if df is None or df.empty:
            return []

        # CRITICAL FIX: Standardize column names to lowercase
        # yfinance returns capitalized columns ['Open', 'High', 'Low', 'Close', 'Volume']
        # but strategies expect lowercase ['open', 'high', 'low', 'close', 'volume']
        df.columns = [str(col).lower() for col in df.columns]

# FIX: Fill NaN volume with 0 for Forex pairs BEFORE processing.
        # Yahoo Finance returns NaN for volume on Forex pairs since there's no central exchange.
        # Without this fix, subsequent code that checks for NaN or uses dropna() would discard all rows.
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0)

        out: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                out.append(
                    {
                        "timestamp": int(idx.timestamp() * 1000) if hasattr(idx, 'timestamp') else int(idx) * 1000,
                        "open": float(row.get("open", 0.0)),
                        "high": float(row.get("high", 0.0)),
                        "low": float(row.get("low", 0.0)),
                        "close": float(row.get("close", 0.0)),
                        "volume": float(row.get("volume", 0.0)),
                    }
                )
            except Exception:
                continue
        return out[-limit:]
    except Exception:
        return []


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Async wrapper that runs the blocking yfinance call in a thread."""
    return await asyncio.to_thread(_sync_get_candles_impl, symbol, timeframe, limit)


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Sync-compatible wrapper that runs the async implementation safely."""
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
