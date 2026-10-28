from __future__ import annotations

from typing import List, Dict, Any
import asyncio

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None

from utils.async_runner import run_sync
from data import provider_diagnostics


def _idx_to_epoch_ms(idx: Any) -> int:
    try:
        if hasattr(idx, "timestamp"):
            return int(float(idx.timestamp()) * 1000)
        raw = str(idx).strip()
        if raw:
            import pandas as pd

            ts = pd.to_datetime(raw, utc=True, errors="coerce")
            if not pd.isna(ts):
                return int(float(ts.timestamp()) * 1000)
    except Exception:
        pass
    return 0


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
        "USOIL": "CL=F",
        "CRUDEOIL": "CL=F",
        # Yahoo's "BRENT" is not Brent crude; production asked for it and got nothing.
        "BRENT": "BZ=F",
        "BRENTUSD": "BZ=F",
        "UKOIL": "BZ=F",
        "XBRUSD": "BZ=F",
        "NATGAS": "NG=F",
        "NAS100": "^NDX",
        "US100": "^NDX",
        "US500": "^GSPC",
        "SPX500": "^GSPC",
        "US30": "^DJI",
        "GER40": "^GDAXI",
        "UK100": "^FTSE",
        "JP225": "^N225",
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
    # Yahoo has no portable 4h interval: build 4h bars from 1h, aligned to UTC.
    resample_4h = str(timeframe).lower() == "4h"
    interval = "1h" if resample_4h else timeframe
    period = "60d" if "d" in timeframe or "h" in timeframe else "7d"

    try:
        t = yf.Ticker(symbol_norm)
        df = t.history(period=period, interval=interval)
        if df is None or df.empty:
            provider_diagnostics.note("yfinance", f"empty_response:{symbol_norm}")
            return []
        if resample_4h:
            index = df.index.tz_convert("UTC") if getattr(df.index, "tz", None) is not None else df.index.tz_localize("UTC")
            df = df.set_index(index).resample("4h", origin="epoch").agg(
                {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
            ).dropna(subset=["Open", "High", "Low", "Close"])
        out: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                ts_ms = _idx_to_epoch_ms(idx)
                out.append(
                    {
                        "time": ts_ms,
                        "timestamp": ts_ms,
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
    except Exception as exc:
        provider_diagnostics.note("yfinance", f"error:{type(exc).__name__}")
        return []


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Async wrapper that runs the blocking yfinance call in a thread."""
    return await asyncio.to_thread(_sync_get_candles_impl, symbol, timeframe, limit)


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Sync-compatible wrapper that runs the async implementation safely."""
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
