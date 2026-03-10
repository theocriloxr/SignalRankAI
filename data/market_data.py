from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable

import yfinance as yf

from data.fetcher import fetch_market_data as fetch_market_data_rest
from db.market_cache import get_recent_candles
from db.session import get_session
import requests
import pandas as pd

logger = logging.getLogger(__name__)


def _convert_to_yfinance_symbol(symbol: str) -> str:
    """Convert project symbol names to yfinance-compatible symbols.

    Examples:
    - BTCUSDT -> BTC-USD
    - EURUSD -> EURUSD=X
    - XAUUSD -> GC=F
    - AAPL -> AAPL
    """
    if not symbol:
        return symbol
    s = str(symbol).upper().strip()

    # Explicit commodity mappings
    commodity_map = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "WTIUSD": "CL=F",
        "CRUDEOIL": "CL=F",
        "NATGAS": "NG=F",
    }
    if s in commodity_map:
        return commodity_map[s]

    # Crypto USDT pairs -> use USD tickers on yfinance
    if s.endswith("USDT") and len(s) > 4:
        base = s[:-4]
        return f"{base}-USD"

    # FX pairs like EURUSD -> EURUSD=X
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        return f"{s}=X"

    # Fallback: return unchanged symbol
    return s


def _fetch_via_yfinance(symbol: str, timeframe: str, limit: int) -> list:
    """Fetch OHLCV data synchronously from yfinance and return list of candles.

    Each candle is a dict with keys: open, high, low, close, volume, timestamp
    Timestamp is seconds since epoch.
    """
    try:
        yf_symbol = _convert_to_yfinance_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)

        # Map timeframe to yfinance interval
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        interval = interval_map.get(str(timeframe), "1h")

        # Request history; rely on tests that mock Ticker.history()
        df = ticker.history(period=None, interval=interval)
        if df is None or df.empty:
            return []

        # Ensure expected column names exist (case-insensitive)
        df_cols = {c.lower(): c for c in df.columns}
        out = []
        for idx, row in df.iterrows():
            try:
                o = row[df_cols.get("open", "Open")]
                h = row[df_cols.get("high", "High")]
                l = row[df_cols.get("low", "Low")]
                c = row[df_cols.get("close", "Close")]
                v = row[df_cols.get("volume", "Volume")]
            except Exception:
                # Skip rows we cannot parse
                continue

            ts = None
            try:
                # pandas.Timestamp -> seconds
                if hasattr(idx, "timestamp"):
                    ts = int(idx.timestamp())
                else:
                    ts = int(pd.to_datetime(idx).timestamp())
            except Exception:
                ts = None

            out.append({
                "open": float(o) if o is not None else 0.0,
                "high": float(h) if h is not None else 0.0,
                "low": float(l) if l is not None else 0.0,
                "close": float(c) if c is not None else 0.0,
                "volume": float(v) if v is not None else 0.0,
                "timestamp": int(ts) if ts is not None else 0,
            })

        # Trim to requested limit if limit provided
        if limit and isinstance(limit, int) and len(out) > limit:
            out = out[-limit:]
        return out
    except Exception:
        return []


def get_realtime_price(symbol: str) -> float | None:
    """Get latest price from yfinance, fallback to Binance REST if needed."""
    try:
        yf_symbol = _convert_to_yfinance_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        # Fast-info may contain lastPrice
        fi = getattr(ticker, "fast_info", None)
        if isinstance(fi, dict) and fi.get("lastPrice") is not None:
            return float(fi.get("lastPrice"))
        # Some versions expose last_price differently
        info = getattr(ticker, "info", None)
        if isinstance(info, dict) and info.get("regularMarketPrice") is not None:
            return float(info.get("regularMarketPrice"))
    except Exception:
        pass

    # Fallback to Binance public API for symbols like BTCUSDT
    try:
        resp = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}")
        if resp.status_code == 200:
            data = resp.json()
            price = data.get("price")
            if price is not None:
                return float(price)
    except Exception:
        pass

    return None


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _timeframe_to_seconds(tf: str) -> int:
    """Convert timeframe string to seconds."""
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(tf, 3600)


def _validate_ohlcv(candles: list) -> bool:
    """Validate OHLCV data integrity.
    
    Returns True if all candles pass validation, False otherwise.
    """
    if not candles:
        return True
    
    for i, c in enumerate(candles):
        try:
            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            close = float(c.get("close", 0))
            
            # Validate high >= low (fundamental relationship)
            if h < l:
                logger.warning(f"OHLCV validation failed at candle {i}: high={h} < low={l}")
                return False
            
            # Validate high >= max(open, close)
            if h < max(o, close):
                logger.warning(f"OHLCV validation failed at candle {i}: high={h} < max(open={o}, close={close})")
                return False
            
            # Validate low <= min(open, close)
            if l > min(o, close):
                logger.warning(f"OHLCV validation failed at candle {i}: low={l} > min(open={o}, close={close})")
                return False
        except (ValueError, TypeError) as e:
            logger.warning(f"OHLCV validation failed at candle {i}: {e}")
            return False
    
    # Validate candles are sorted by timestamp ascending
    timestamps = []
    for c in candles:
        ts = c.get("timestamp")
        if ts is not None:
            # Handle both ms and seconds
            ts_val = int(ts) if isinstance(ts, (int, float)) else 0
            if ts_val > 10**12:  # milliseconds
                ts_val = ts_val // 1000
            timestamps.append(ts_val)
    
    if timestamps and timestamps != sorted(timestamps):
        logger.warning("OHLCV validation failed: candles not sorted by timestamp ascending")
        return False
    
    return True


def _check_staleness(candles: list, timeframe: str) -> tuple[bool, float]:
    """Check if cached candles are stale.
    
    Returns (is_fresh, data_age_seconds).
    Candles are stale if the latest candle is older than 2× the timeframe interval.
    """
    if not candles:
        return False, 0.0
    
    # Get the latest candle's timestamp
    latest_candle = candles[-1]
    ts = latest_candle.get("timestamp")
    
    if ts is None:
        logger.warning(f"Staleness check failed for {timeframe}: no timestamp in latest candle")
        return False, 0.0
    
    # Convert timestamp to seconds
    try:
        ts_val = int(ts) if isinstance(ts, (int, float)) else 0
        if ts_val > 10**12:  # milliseconds
            ts_val = ts_val // 1000
        
        current_time = time.time()
        data_age = current_time - ts_val
        
        # Calculate staleness threshold (2× timeframe interval)
        tf_seconds = _timeframe_to_seconds(timeframe)
        threshold = 2 * tf_seconds
        
        is_fresh = data_age <= threshold
        
        if not is_fresh:
            logger.warning(
                f"Staleness check failed for {timeframe}: "
                f"data age={data_age:.0f}s exceeds threshold={threshold}s (2×{tf_seconds}s)"
            )
        
        return is_fresh, data_age
    except (ValueError, TypeError) as e:
        logger.warning(f"Staleness check failed for {timeframe}: {e}")
        return False, 0.0


async def fetch_market_data_cached(asset: str, timeframes: Iterable[str]) -> dict:
    """Fetch market data from yfinance first, then Postgres cache, then fallback to REST.

    Priority order:
    1. yfinance (primary source for all assets)
    2. Postgres cache (from WS ingestor)
    3. REST providers (Binance/Bybit/etc)
    """

    tfs = [str(tf).strip() for tf in (timeframes or []) if str(tf).strip()]
    if not tfs:
        return {}

    want = _env_int("MARKET_CACHE_MIN_CANDLES", 80)
    limit = _env_int("MARKET_CACHE_READ_LIMIT", 200)
    use_cache = _env_bool("MARKET_CACHE_ENABLED", True)
    use_yfinance = _env_bool("YFINANCE_ENABLED", True)

    out: dict = {}
    
    # 1. Try yfinance first (primary source)
    if use_yfinance:
        for tf in tfs:
            try:
                yf_candles = await asyncio.to_thread(_fetch_via_yfinance, asset, tf, limit)
                if yf_candles and len(yf_candles) >= want:
                    # Add data age calculation
                    if yf_candles:
                        latest_ts = yf_candles[-1].get("timestamp", 0)
                        data_age = int(_time.time() - latest_ts) if latest_ts > 0 else None
                    else:
                        data_age = None
                    
                    out[tf] = {
                        "candles": yf_candles,
                        "source": "yfinance",
                        "data_age_seconds": data_age
                    }
                    logger.info(f"[market_data] yfinance success for {asset} {tf}: {len(yf_candles)} candles")
                else:
                    logger.warning(f"yfinance failed/insufficient for {asset} {tf}, falling back to cache/REST")
            except Exception as e:
                logger.warning(f"yfinance exception for {asset} {tf}: {e}")

    # 2. Try cache for missing timeframes
    missing_after_yf = [tf for tf in tfs if tf not in out]
    if use_cache and missing_after_yf:
        try:
            async with get_session() as session:
                for tf in missing_after_yf:
                    candles = await get_recent_candles(session, symbol=asset, timeframe=tf, limit=limit)
                    if candles:
                        logger.info(f"[market_data] asset={asset} tf={tf} candles_fetched={len(candles)}")
                    
                    if candles and len(candles) >= want:
                        # Validate OHLCV
                        if not _validate_ohlcv(candles):
                            logger.warning(f"Cached candles for {asset} {tf} failed OHLCV validation, skipping cache")
                            continue
                        
                        # Check staleness
                        is_fresh, data_age = _check_staleness(candles, tf)
                        if not is_fresh:
                            logger.warning(f"Cached candles for {asset} {tf} are stale (age={data_age:.0f}s), skipping cache")
                            continue
                        
                        # Cache is valid
                        out[tf] = {
                            "candles": candles,
                            "data_age_seconds": data_age
                        }
                await session.commit()
        except Exception:
            out = out or {}

    # 3. Backfill still-missing timeframes via REST fetcher
    missing = [tf for tf in tfs if tf not in out]
    if missing:
        # Fallback providers (CryptoCompare/Bybit) can be slower when Binance is blocked; allow longer by default.
        rest_timeout = float(_env_int("MARKET_REST_TIMEOUT_SECONDS", 60))
        try:
            rest = await asyncio.wait_for(
                asyncio.to_thread(fetch_market_data_rest, asset, missing),
                timeout=max(1.0, rest_timeout),
            )
        except asyncio.TimeoutError:
            rest = {}
        
        # Validate and add data_age_seconds for REST data
        for tf, payload in (rest or {}).items():
            candles = (payload or {}).get("candles") or []
            
            # Validate OHLCV for REST candles
            if candles and not _validate_ohlcv(candles):
                logger.warning(f"REST candles for {asset} {tf} failed OHLCV validation, skipping")
                continue
            
            # Calculate data age for REST candles (note: REST data is freshly fetched,
            # so we don't reject it for staleness, only report age for monitoring)
            if candles:
                _, data_age = _check_staleness(candles, tf)
                if "data_age_seconds" not in payload:
                    payload["data_age_seconds"] = data_age
            
            out[tf] = payload

        # Best-effort write-through into Postgres cache tables.
        if _env_bool("MARKET_CACHE_WRITE_THROUGH", True):
            try:
                from datetime import datetime
                from db.market_cache import upsert_market_candle, upsert_market_tick

                def _ts_to_ms(v):
                    if v is None:
                        return None
                    if isinstance(v, (int, float)):
                        # Heuristic: < 10^12 likely seconds.
                        n = int(v)
                        return n * 1000 if n < 1_000_000_000_000 else n
                    s = str(v).strip()
                    if not s:
                        return None
                    try:
                        # AlphaVantage returns ISO without timezone; treat as UTC.
                        dt = datetime.fromisoformat(s.replace("Z", ""))
                        return int(dt.timestamp() * 1000)
                    except Exception:
                        return None

                async with get_session() as session:
                    last_tick_ms = None
                    last_tick_price = None
                    for tf, payload in (rest or {}).items():
                        candles = (payload or {}).get("candles") or []
                        for c in candles:
                            try:
                                ts_ms = _ts_to_ms(c.get("timestamp"))
                                if ts_ms is None:
                                    continue
                                await upsert_market_candle(
                                    session,
                                    symbol=str(asset),
                                    timeframe=str(tf),
                                    open_time_ms=int(ts_ms),
                                    open=float(c.get("open")),
                                    high=float(c.get("high")),
                                    low=float(c.get("low")),
                                    close=float(c.get("close")),
                                    volume=float(c.get("volume") or 0.0),
                                    is_final=True,
                                )
                                last_tick_ms = int(ts_ms)
                                last_tick_price = float(c.get("close"))
                            except Exception:
                                continue
                    if last_tick_price is not None:
                        try:
                            await upsert_market_tick(
                                session,
                                symbol=str(asset),
                                price=float(last_tick_price),
                                event_time_ms=int(last_tick_ms) if last_tick_ms is not None else None,
                            )
                        except Exception:
                            pass
                    await session.commit()
            except Exception:
                pass

    # If cache returned candles without indicators, compute them using existing fetcher pipeline:
    # easiest: re-run calculate_indicators for cached candles.
    try:
        from data.indicators import calculate_indicators

        for tf in list(out.keys()):
            payload = out.get(tf) or {}
            if "indicators" not in payload:
                candles = payload.get("candles") or []
                if candles:
                    payload["indicators"] = calculate_indicators(candles)
                    out[tf] = payload
    except Exception:
        pass

    return out
