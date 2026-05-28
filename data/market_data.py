from __future__ import annotations

import asyncio
import logging
import os
import time as _time
import time
from typing import Iterable

import yfinance as yf

from data.fetcher import async_get_candles
from db.market_cache import get_recent_candles
from db.session import get_session
import requests
import pandas as pd
from core.redis_state import state
import httpx

logger = logging.getLogger(__name__)

_YF_COOLDOWN_UNTIL = 0.0


def _yf_timeout_seconds() -> float:
    try:
        return float((os.getenv("YFINANCE_TIMEOUT_SECONDS") or "6").strip())
    except Exception:
        return 6.0


def _yf_cooldown_seconds() -> float:
    try:
        return float((os.getenv("YFINANCE_COOLDOWN_SECONDS") or "120").strip())
    except Exception:
        return 120.0


def _yf_available() -> bool:
    return time.time() >= float(_YF_COOLDOWN_UNTIL or 0.0)


def _set_yf_cooldown(reason: str) -> None:
    global _YF_COOLDOWN_UNTIL
    _YF_COOLDOWN_UNTIL = time.time() + _yf_cooldown_seconds()
    logger.warning("[market_data] yfinance cooldown set: %s", reason)


async def _fetch_yfinance_with_timeout(asset: str, tf: str, limit: int) -> list:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_via_yfinance, asset, tf, limit),
            timeout=_yf_timeout_seconds(),
        )
    except asyncio.TimeoutError:
        _set_yf_cooldown("timeout")
        return []
    except Exception as exc:
        _set_yf_cooldown(str(exc))
        return []


async def _tradingview_indicators(asset: str, tf: str) -> dict:
    if not _env_bool("TRADINGVIEW_ENABLED", True):
        return {}
    try:
        from tradingview_ta import TA_Handler, Interval
    except Exception:
        return {}

    tf_map = {
        "1m": Interval.INTERVAL_1_MINUTE,
        "5m": Interval.INTERVAL_5_MINUTES,
        "15m": Interval.INTERVAL_15_MINUTES,
        "1h": Interval.INTERVAL_1_HOUR,
        "4h": Interval.INTERVAL_4_HOURS,
        "1d": Interval.INTERVAL_1_DAY,
    }
    tv_tf = tf_map.get(str(tf).lower().strip())
    if tv_tf is None:
        return {}

    try:
        asset_upper = str(asset or "").upper().strip()
        if asset_upper.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH")):
            exchange = "BINANCE"
            screener = "crypto"
            symbol = asset_upper
        else:
            exchange = "FX_IDC"
            screener = "forex"
            symbol = asset_upper

        handler = TA_Handler(
            symbol=symbol,
            screener=screener,
            exchange=exchange,
            interval=tv_tf,
        )
        analysis = handler.get_analysis()
        indicators = getattr(analysis, "indicators", None)
        if isinstance(indicators, dict):
            return indicators
    except Exception:
        return {}
    return {}

# yfinance can emit noisy symbol-level errors during fallback; keep app logs readable.
try:
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Unified ticker formatter — maps canonical SignalRankAI symbols to each
# provider's required format. Use this instead of ad-hoc conversions.
# ---------------------------------------------------------------------------

_BINANCE_OVERRIDES: dict[str, str] = {
    "XAUUSD": "XAUUSDT",
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}

_OANDA_OVERRIDES: dict[str, str] = {
    "XAUUSD": "XAU_USD",
    "XAGUSD": "XAG_USD",
    "BTCUSD": "BTC_USD",
    "ETHUSD": "ETH_USD",
}

_YFINANCE_OVERRIDES: dict[str, str] = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "WTIUSD": "CL=F",
    "CRUDEOIL": "CL=F",
    "NATGAS": "NG=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "BNBUSD": "BNB-USD",
    "SOLUSD": "SOL-USD",
}

_METAAPI_OVERRIDES: dict[str, str] = {
    "XAUUSD": "XAUUSD",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
}


def format_ticker(symbol: str, provider: str = "yfinance") -> str:
    """Convert a canonical SignalRankAI symbol to the format required by a given provider.

    Args:
        symbol:   Canonical symbol, e.g. ``"BTCUSDT"``, ``"EURUSD"``, ``"XAUUSD"``.
        provider: One of ``"yfinance"``, ``"binance"``, ``"oanda"``, ``"metaapi"``,
                  ``"polygon"``, ``"twelvedata"``, ``"alphavantage"``.

    Returns:
        The provider-specific ticker string.

    Examples:
        >>> format_ticker("XAUUSD", "yfinance")
        'GC=F'
        >>> format_ticker("BTCUSDT", "binance")
        'BTCUSDT'
        >>> format_ticker("EURUSD", "oanda")
        'EUR_USD'
        >>> format_ticker("AAPL", "polygon")
        'AAPL'
    """
    if not symbol:
        return symbol
    s = str(symbol).upper().strip()
    p = str(provider).lower().strip()

    if p == "yfinance":
        if s in _YFINANCE_OVERRIDES:
            return _YFINANCE_OVERRIDES[s]
        # FX pairs like EURUSD must map to EURUSD=X (not EUR-USD).
        if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
            return f"{s}=X"
        if s.endswith("USDT") and len(s) > 4:
            return f"{s[:-4]}-USD"
        if s.endswith("USD") and len(s) > 3 and s[:3].isalpha() and s[3:] == "USD":
            return f"{s[:-3]}-USD"
        return s

    if p == "binance":
        if s in _BINANCE_OVERRIDES:
            return _BINANCE_OVERRIDES[s]
        if s.endswith("-USD"):
            return s[:-4] + "USDT"
        return s

    if p == "oanda":
        if s in _OANDA_OVERRIDES:
            return _OANDA_OVERRIDES[s]
        if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
            return f"{s[:3]}_{s[3:]}"
        return s

    if p == "metaapi":
        return _METAAPI_OVERRIDES.get(s, s)

    if p in ("polygon", "twelvedata", "alphavantage"):
        if s.endswith("USDT"):
            return s[:-1]  # BTCUSDT -> BTCUST  — callers apply their own suffix
        if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
            return f"{s[:3]}/{s[3:]}"
        return s

    return s


# ---------------------------------------------------------------------------
# Async circuit-breaker waterfall for OHLCV fetching
# ---------------------------------------------------------------------------

async def fetch_candles_with_circuit_breaker(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 2.5,
) -> list:
    """Fetch OHLCV data with async circuit-breaker fallback chain.

    Priority:
        1. Binance REST (fastest for crypto; 3 s timeout)
        2. yfinance (universal; 3 s timeout)
        3. MetaApi live price only (price-only stub for non-zero return)

    Each provider is wrapped in ``asyncio.wait_for(..., timeout=2.5)`` so a
    hanging upstream never blocks the engine.
    """

    async def _try_binance() -> list:
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={format_ticker(symbol, 'binance')}"
            f"&interval={timeframe}&limit={min(limit, 1000)}"
        )
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.json()
            candles = []
            for k in raw:
                candles.append({
                    "timestamp": int(k[0]) // 1000,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return candles

    async def _try_yfinance() -> list:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_via_yfinance, symbol, timeframe, limit),
            timeout=timeout,
        )

    # 1 — Binance (crypto only; skip for FX/commodities)
    if symbol.endswith("USDT") or symbol.endswith("BTC") or symbol.endswith("ETH"):
        try:
            candles = await asyncio.wait_for(_try_binance(), timeout=timeout)
            if candles:
                logger.debug(f"[circuit_breaker] Binance OK for {symbol} {timeframe}")
                return candles
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(f"[circuit_breaker] Binance failed for {symbol}: {exc}; trying yfinance")

    # 2 — yfinance
    try:
        candles = await _try_yfinance()
        if candles:
            logger.debug(f"[circuit_breaker] yfinance OK for {symbol} {timeframe}")
            return candles
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning(f"[circuit_breaker] yfinance failed for {symbol}: {exc}")

    logger.error(f"[circuit_breaker] All providers failed for {symbol} {timeframe}")
    return []


# ---------------------------------------------------------------------------
# Order-block / FVG detection (appends is_near_order_block flag)
# ---------------------------------------------------------------------------

def detect_order_blocks(candles: list, lookback: int = 100) -> bool:
    """Scan the last ``lookback`` candles for Fair Value Gaps / Imbalances.

    An FVG exists when candle[i-2].high < candle[i].low (bullish) or
    candle[i-2].low > candle[i].high (bearish) — leaving an unfilled gap.

    Returns True if the current price (last close) sits within 0.5% of any FVG.
    """
    if not candles or len(candles) < 3:
        return False
    recent = candles[-lookback:] if len(candles) > lookback else candles
    try:
        current_price = float(recent[-1].get("close", 0))
        if current_price <= 0:
            return False
        for i in range(2, len(recent)):
            prev2_high = float(recent[i - 2].get("high", 0))
            prev2_low = float(recent[i - 2].get("low", 0))
            curr_low = float(recent[i].get("low", 0))
            curr_high = float(recent[i].get("high", 0))
            # Bullish FVG: gap between candle[i-2].high and candle[i].low
            if prev2_high < curr_low:
                mid = (prev2_high + curr_low) / 2
                if abs(current_price - mid) / current_price <= 0.005:
                    return True
            # Bearish FVG: gap between candle[i].high and candle[i-2].low
            if curr_high < prev2_low:
                mid = (curr_high + prev2_low) / 2
                if abs(current_price - mid) / current_price <= 0.005:
                    return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Legacy shim — kept for callers that have not been updated yet
# ---------------------------------------------------------------------------

def _convert_to_yfinance_symbol(symbol: str) -> str:
    """Deprecated: use ``format_ticker(symbol, 'yfinance')`` instead."""
    return format_ticker(symbol, "yfinance")


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
    
    # Allow tiny floating-point tolerance to avoid false negatives from providers.
    eps = 1e-6

    for i, c in enumerate(candles):
        try:
            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            close = float(c.get("close", 0))
            
            # Validate high >= low (fundamental relationship)
            if h + eps < l:
                logger.warning(f"OHLCV validation failed at candle {i}: high={h} < low={l}")
                return False
            
            # Validate high >= max(open, close)
            if h + eps < max(o, close):
                logger.warning(f"OHLCV validation failed at candle {i}: high={h} < max(open={o}, close={close})")
                return False
            
            # Validate low <= min(open, close)
            if l - eps > min(o, close):
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


def _sanitize_ohlcv(candles: list) -> list:
    """Normalize candle OHLC values to prevent minor provider inconsistencies.

    Ensures: high >= max(open, close) and low <= min(open, close).
    Rows that cannot be parsed are dropped.
    """
    if not candles:
        return candles

    out: list = []
    for c in candles:
        try:
            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            close = float(c.get("close", 0))

            h = max(h, o, close)
            l = min(l, o, close)

            nc = dict(c)
            nc["open"] = o
            nc["high"] = h
            nc["low"] = l
            nc["close"] = close
            out.append(nc)
        except Exception:
            continue
    return out


def _check_staleness(candles: list, timeframe: str) -> tuple[bool, float]:
    """Check if cached candles are stale.
    
    Returns (is_fresh, data_age_seconds).
    Candles are stale if the latest candle is older than 2× the timeframe interval.
    """
    if not candles:
        return False, 0.0
    
    def _to_epoch_seconds(value) -> int | None:
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)):
                ts_val = int(float(value))
                return ts_val // 1000 if ts_val > 10**12 else ts_val
            raw = str(value).strip()
            if not raw:
                return None
            if raw.replace(".", "", 1).isdigit():
                ts_val = int(float(raw))
                return ts_val // 1000 if ts_val > 10**12 else ts_val
            dt = pd.to_datetime(raw, utc=True, errors="coerce")
            if pd.isna(dt):
                return None
            return int(dt.timestamp())
        except Exception:
            return None

    # Get the latest candle's timestamp
    latest_candle = candles[-1]
    ts = latest_candle.get("timestamp")
    
    if ts is None:
        logger.warning(f"Staleness check failed for {timeframe}: no timestamp in latest candle")
        return False, 0.0
    
    # Convert timestamp to seconds
    try:
        ts_val = _to_epoch_seconds(ts)
        if ts_val is None or ts_val <= 0:
            raise ValueError(f"invalid timestamp: {ts!r}")
        
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
    if use_yfinance and _yf_available():
        for tf in tfs:
            try:
                yf_candles = await _fetch_yfinance_with_timeout(asset, tf, limit)
                if yf_candles and len(yf_candles) >= want:
                    yf_candles = _sanitize_ohlcv(yf_candles)
                    # Add data age calculation
                    if yf_candles:
                        latest_ts = _check_staleness(yf_candles, tf)[1]
                        data_age = int(latest_ts) if latest_ts and latest_ts > 0 else None
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
    elif use_yfinance and not _yf_available():
        logger.warning("[market_data] yfinance skipped due to cooldown")

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
                        candles = _sanitize_ohlcv(candles)
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

    # 3. Backfill still-missing timeframes via async provider waterfall
    missing = [tf for tf in tfs if tf not in out]
    if missing:
        rest: dict = {}
        rest_timeout = float(_env_int("MARKET_REST_TIMEOUT_SECONDS", 60))

        async def _fetch_one(tf: str):
            try:
                strict_timeout = min(2.5, max(0.1, rest_timeout))
                candles = await asyncio.wait_for(
                    async_get_candles(asset, tf),
                    timeout=strict_timeout,
                )
                if candles:
                    return tf, {
                        "candles": candles,
                        "source": "provider_fallback_chain",
                    }
            except asyncio.TimeoutError:
                logger.warning(f"[market_data] provider waterfall timeout for {asset} {tf}")
            except Exception as e:
                logger.warning(f"[market_data] provider waterfall failed for {asset} {tf}: {e}")
            return tf, {}

        fetched = await asyncio.gather(*[_fetch_one(tf) for tf in missing], return_exceptions=False)
        rest = {tf: payload for tf, payload in fetched if payload}
        
        # Validate and add data_age_seconds for REST data
        for tf, payload in (rest or {}).items():
            candles = (payload or {}).get("candles") or []
            if candles:
                candles = _sanitize_ohlcv(candles)
                payload["candles"] = candles
            
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

            # Attach lightweight alternative-market signals (funding/open-interest/orderbook)
            try:
                async def _fetch_alt():
                    try:
                        sym = str(asset or "").upper().strip()
                        macro: dict = {}
                        # Only attempt for crypto perpetual-like symbols ending with USDT
                        if sym.endswith("USDT"):
                            bid_vol = ask_vol = 0.0
                            try:
                                async with httpx.AsyncClient(timeout=2.0) as client:
                                    bin_sym = format_ticker(sym, "binance")
                                    # Funding rate (recent)
                                    fr_url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={bin_sym}&limit=1"
                                    r = await client.get(fr_url)
                                    if r.status_code == 200:
                                        j = r.json()
                                        if isinstance(j, list) and j:
                                            fr = j[0].get("fundingRate")
                                            macro["funding_rate"] = float(fr) if fr is not None else 0.0
                                    # Open interest
                                    oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={bin_sym}"
                                    r2 = await client.get(oi_url)
                                    if r2.status_code == 200:
                                        j2 = r2.json()
                                        oi = j2.get("openInterest")
                                        try:
                                            current_oi = float(oi)
                                        except Exception:
                                            current_oi = 0.0
                                        prev_raw = state.get_sync(f"market:open_interest:{bin_sym}")
                                        prev = None
                                        try:
                                            prev = float(prev_raw) if prev_raw is not None else None
                                        except Exception:
                                            prev = None
                                        if prev and prev > 0:
                                            macro["open_interest_change"] = (current_oi - prev) / prev
                                        else:
                                            macro["open_interest_change"] = 0.0
                                        try:
                                            state.set_sync(f"market:open_interest:{bin_sym}", str(current_oi))
                                        except Exception:
                                            pass
                                    # Orderbook imbalance (top levels)
                                    depth_url = f"https://api.binance.com/api/v3/depth?symbol={bin_sym}&limit=5"
                                    r3 = await client.get(depth_url)
                                    if r3.status_code == 200:
                                        j3 = r3.json()
                                        bids = j3.get("bids") or []
                                        asks = j3.get("asks") or []
                                        bid_vol = sum(float(b[1]) for b in bids[:5]) if bids else 0.0
                                        ask_vol = sum(float(a[1]) for a in asks[:5]) if asks else 0.0
                                        if (bid_vol + ask_vol) > 0:
                                            macro["orderbook_imbalance"] = (bid_vol - ask_vol) / (bid_vol + ask_vol)
                                        else:
                                            macro["orderbook_imbalance"] = 0.0
                            except Exception:
                                pass
                        # Default zeros for non-crypto or failures
                        macro.setdefault("funding_rate", 0.0)
                        macro.setdefault("open_interest_change", 0.0)
                        macro.setdefault("orderbook_imbalance", 0.0)
                        macro.setdefault("news_sentiment", 0.0)
                        return macro
                    except Exception:
                        return {"funding_rate": 0.0, "open_interest_change": 0.0, "orderbook_imbalance": 0.0, "news_sentiment": 0.0}

                macro = await _fetch_alt()
                # Attach macro into each timeframe payload for ML helpers to consume
                for tf, payload in list(out.items()):
                    if not isinstance(payload, dict):
                        continue
                    payload.setdefault("_macro", {})
                    # Merge top-level macro fields without overwriting existing keys
                    for k, v in macro.items():
                        payload["_macro"].setdefault(k, v)
                # Also expose a root-level _macro so callers that pass the whole
                # market_data mapping (e.g. engine.core.extract_features) can read it.
                try:
                    out.setdefault("_macro", {})
                    for k, v in macro.items():
                        out["_macro"].setdefault(k, v)
                except Exception:
                    pass
            except Exception:
                pass

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

    # TradingView enrichment (indicator-only overlay).
    try:
        for tf in list(out.keys()):
            payload = out.get(tf) or {}
            candles = payload.get("candles") or []
            if not candles:
                continue
            tv_ind = await _tradingview_indicators(asset, tf)
            if tv_ind:
                ind = payload.get("indicators") or {}
                for k, v in tv_ind.items():
                    ind[f"tv_{k}"] = v
                payload["indicators"] = ind
                payload["tradingview_enriched"] = True
                out[tf] = payload
    except Exception:
        pass

    return out
