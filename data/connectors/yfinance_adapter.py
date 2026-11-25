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
        # 4 Nov 2026: these four reached Yahoo as their own names ("HK50"), which
        # returns nothing (`empty_response:HK50` every scan during the Hong Kong
        # session), so they had no candles on any timeframe. Same symbols as
        # services/asset_mapper.py.
        "FRA40": "^FCHI",
        "EU50": "^STOXX50E",
        "AUS200": "^AXJO",
        "HK50": "^HSI",
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


# 25 Nov 2026: every scan downloaded 5m, 15m, 1h, 4h (the same 60 days of 1h again) and 1d for
# ~60 assets with no cache, and Yahoo answered HTTP 429 to both candles and the live quotes the
# delivery check needs, so index/FX/metal signals were blocked with quote_unavailable. Downloads
# are now cached per (symbol, interval, period) for a fraction of the bar length, far inside each
# timeframe's freshness limit (2x the bar), and 4h reuses the 1h download.
import os
import threading
import time

_HISTORY_CACHE: dict[tuple[str, str, str], tuple[float, Any]] = {}
_HISTORY_LOCK = threading.Lock()
_TTL_SECONDS = {"1m": 4, "5m": 60, "15m": 150, "30m": 300, "1h": 600, "1d": 3600}


def _ttl(interval: str) -> float:
    scale = float(os.getenv("YFINANCE_HISTORY_CACHE_SCALE", "1") or 1)
    return max(0.0, _TTL_SECONDS.get(interval, 60) * scale)


def _history(symbol_norm: str, interval: str, period: str):
    return _history_with_meta(symbol_norm, interval, period)[0]


def _history_with_meta(symbol_norm: str, interval: str, period: str):
    """(DataFrame, Yahoo chart metadata such as regularMarketPrice/regularMarketTime)."""
    key = (symbol_norm, interval, period)
    now = time.monotonic()
    with _HISTORY_LOCK:
        hit = _HISTORY_CACHE.get(key)
        if hit and now - hit[0] < _ttl(interval):
            return hit[1], (hit[2] if len(hit) > 2 else {})
    ticker = yf.Ticker(symbol_norm)
    df = ticker.history(period=period, interval=interval)
    try:
        meta = dict(getattr(ticker, "history_metadata", None) or {})
    except Exception:
        meta = {}
    if df is not None and not df.empty:
        with _HISTORY_LOCK:
            _HISTORY_CACHE[key] = (time.monotonic(), df, meta)
            if len(_HISTORY_CACHE) > 2048:
                for stale in sorted(_HISTORY_CACHE, key=lambda k: _HISTORY_CACHE[k][0])[:512]:
                    _HISTORY_CACHE.pop(stale, None)
    return df, meta


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
        df = _history(symbol_norm, interval, period)
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
