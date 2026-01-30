from __future__ import annotations

from typing import List, Dict, Any
import asyncio

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None

from utils.async_runner import run_sync


def _normalize_symbol(symbol: str) -> str:
    # Common mapping: BTCUSDT -> BTC-USD, ETHUSDT -> ETH-USD
    s = symbol.strip()
    if s.upper().endswith("USDT"):
        base = s[:-4]
        return f"{base}-USD"
    if len(s) >= 4 and s[-3:] == "USD" and "-" not in s:
        return s[:-3] + "-USD"
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
