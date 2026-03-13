from __future__ import annotations

from typing import List, Dict, Any
import asyncio

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None

from utils.async_runner import run_sync


def _normalize_symbol(symbol: str) -> str:
    # Unified mapping to Yahoo-compatible symbols.
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
        crypto_bases = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "MATIC"}
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
        out: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                out.append(
                    {
                        "time": idx,
                        "open": float(row.get("Open", 0.0)),
                        "high": float(row.get("High", 0.0)),
                        "low": float(row.get("Low", 0.0)),
                        "close": float(row.get("Close", 0.0)),
                        "volume": float(row.get("Volume", 0.0)),
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
