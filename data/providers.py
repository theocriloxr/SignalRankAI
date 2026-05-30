"""
Multi-provider data fetching with automatic waterfall fallbacks.

Waterfall order:
    Crypto:      Yahoo Finance -> Binance -> CoinGecko
    Forex:       Yahoo Finance -> OANDA -> Twelve Data -> Polygon
    Commodity:   Yahoo Finance -> AlphaVantage -> Twelve Data
    Stock:       Yahoo Finance -> AlphaVantage -> Polygon -> Twelve Data

Supports: Polygon.io, Twelve Data, Yahoo Finance, OANDA, TradingView.
"""

import os
import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
from utils.async_runner import run_sync
from utils import proxy_manager

logger = logging.getLogger(__name__)

# Reduce noisy provider-internal logs (we already emit our own structured logs).
try:
    _yf_logger = logging.getLogger("yfinance")
    _yf_logger.setLevel(logging.CRITICAL)
    _yf_logger.propagate = False
except Exception:
    pass

# Rate limiting state
_PROVIDER_LAST_CALL = {}
_PROVIDER_COOLDOWN = {}
_CANDLES_CACHE: dict[str, tuple[float, list]] = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default) or default)
    except Exception:
        return float(default)


def _set_cooldown(provider: str, seconds: float) -> None:
    try:
        _PROVIDER_COOLDOWN[provider] = time.monotonic() + max(0.0, float(seconds or 0.0))
    except Exception:
        _PROVIDER_COOLDOWN[provider] = time.monotonic() + float(seconds or 0.0)


def _is_cooldown_active(provider: str) -> bool:
    try:
        until = float(_PROVIDER_COOLDOWN.get(provider) or 0.0)
        return until > time.monotonic()
    except Exception:
        return False


def _rate_limit(provider: str, wait: float) -> None:
    try:
        last = float(_PROVIDER_LAST_CALL.get(provider) or 0.0)
        now = time.monotonic()
        elapsed = now - last if last else None
        if elapsed is not None and elapsed < float(wait or 0.0):
            time.sleep(float(wait or 0.0) - elapsed)
    except Exception:
        pass
    finally:
        _PROVIDER_LAST_CALL[provider] = time.monotonic()


def _cache_key(symbol: str, timeframe: str) -> str:
    return f"candles:{(symbol or '').upper()}:{(timeframe or '')}"


def _set_candles_cache(symbol: str, timeframe: str, candles: list) -> None:
    try:
        _CANDLES_CACHE[_cache_key(symbol, timeframe)] = (time.monotonic(), list(candles or []))
    except Exception:
        pass


def get_candles(symbol: str, timeframe: str, limit: int = 200):
    """Simplified primary candle fetcher used as a safe fallback.

    This lightweight implementation prefers CCXT Binance (with proxy support)
    and otherwise returns an empty list. The original file contains a larger
    waterfall of providers; for the purposes of proxy tests and safe imports
    we keep this minimal and non-blocking.
    """
    try:
        result = fetch_binance_ccxt_candles(symbol, timeframe, limit=limit)
        if result and len(result) >= 1:
            return result[-limit:]
    except Exception:
        pass
    return []


def _get_candles_cache(symbol: str, timeframe: str, max_age_s: float = 300.0):
    return []
def _rate_limit_cooldown_seconds(provider: str, *, status_code: int | None = None, message: str = "") -> float | None:
    msg = (message or "").lower()
    if provider == "twelvedata":
        if status_code == 429 or any(term in msg for term in ("run out of api credits", "daily limit", "credit limit", "rate limit")):
            return _env_float("TWELVEDATA_RATE_LIMIT_COOLDOWN_SECONDS", 12 * 60 * 60)
    elif provider == "polygon":
        if status_code == 429 or any(term in msg for term in ("rate limit", "too many requests", "throttle")):
            return _env_float("POLYGON_RATE_LIMIT_COOLDOWN_SECONDS", 60 * 60)
    elif status_code == 429:
        return _env_float(f"{provider.upper()}_RATE_LIMIT_COOLDOWN_SECONDS", 60.0)
    return None


def _maybe_apply_rate_limit_cooldown(provider: str, *, status_code: int | None = None, message: str = "") -> bool:
    cooldown_seconds = _rate_limit_cooldown_seconds(provider, status_code=status_code, message=message)
    if cooldown_seconds is None:
        return False
    _set_cooldown(provider, cooldown_seconds)
    return True


def _normalize_binance_symbol(symbol: str) -> str:
    sym = (symbol or "").upper().strip().replace("/", "").replace("-", "")
    if sym.endswith("USD") and not sym.endswith("USDT"):
        sym = sym[:-3] + "USDT"
    return sym


def _map_binance_timeframe(timeframe: str) -> str:
    return {
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }.get((timeframe or "").strip(), "1h")


def _fetch_binance_ccxt_sync(symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
    try:
        import ccxt  # type: ignore
    except Exception:
        return []


_COINGECKO_ID_CACHE: dict[str, str] = {}


def _coingecko_symbol_to_id(symbol: str) -> Optional[str]:
    key = (symbol or "").upper().strip()
    if not key:
        return None
    if key in _COINGECKO_ID_CACHE:
        return _COINGECKO_ID_CACHE[key]
    # Common quick map
    common = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "ADA": "cardano",
        "BNB": "binancecoin",
        "USDT": "tether",
        "DOT": "polkadot",
        "DOGE": "dogecoin",
    }
    if key in common:
        _COINGECKO_ID_CACHE[key] = common[key]
        return common[key]
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=5)
        if resp.ok:
            data = resp.json()
            for item in data or []:
                sym = (item.get("symbol") or "").upper()
                if sym == key:
                    _COINGECKO_ID_CACHE[key] = item.get("id")
                    return item.get("id")
    except Exception:
        pass
    return None


def fetch_coingecko_market_chart(symbol: str, days: int = 7) -> List[Dict]:
    """Fetch simple market chart (prices) from CoinGecko as a lightweight OHLCV fallback.

    Returns a list of dicts with timestamp (ms), open/high/low/close/volume where available.
    """
    try:
        coin_id = _coingecko_symbol_to_id(symbol)
        if not coin_id:
            return []
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": int(days)}
        resp = requests.get(url, params=params, timeout=8)
        if not resp.ok:
            return []
        data = resp.json() or {}
        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        # Build candles by grouping by day (approximate)
        out: List[Dict] = []
        for i in range(len(prices)):
            try:
                ts = int(prices[i][0])
                price = float(prices[i][1])
                vol = float(volumes[i][1]) if i < len(volumes) else 0.0
                out.append({"timestamp": ts, "open": price, "high": price, "low": price, "close": price, "volume": vol})
            except Exception:
                continue
        return out
    except Exception:
        return []


def fetch_coingecko_price(symbol: str) -> Optional[float]:
    try:
        coin_id = _coingecko_symbol_to_id(symbol)
        if not coin_id:
            return None
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": "usd", "include_24hr_vol": "true"}
        resp = requests.get(url, params=params, timeout=5)
        if not resp.ok:
            return None
        data = resp.json() or {}
        return float((data.get(coin_id) or {}).get("usd"))
    except Exception:
        return None


def fetch_cryptopanic_news(limit: int = 10, currencies: Optional[List[str]] = None) -> List[Dict]:
    """Fetch recent crypto news from CryptoPanic (if API token provided)."""
    api_key = os.getenv("CRYPTOPANIC_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {"auth_token": api_key, "public": "true", "kind": "news", "limit": int(limit)}
        if currencies:
            params["currencies"] = ",".join(currencies)
        resp = requests.get(url, params=params, timeout=8)
        if not resp.ok:
            return []
        data = resp.json() or {}
        posts = data.get("results") or data.get("results", [])
        out = []
        for p in posts or []:
            try:
                out.append({
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "domain": p.get("domain"),
                    "published_at": p.get("published_at"),
                    "votes": p.get("votes"),
                    "url": p.get("url"),
                })
            except Exception:
                continue
        return out
    except Exception:
        return []

    try:
        proxy_url = (
            (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip()
            or proxy_manager.get_proxy_sync()
        )
        exchange_config: dict = {
            "enableRateLimit": True,
            "timeout": 2500,
        }
        if proxy_url:
            exchange_config["proxies"] = {"http": proxy_url, "https": proxy_url}
            exchange_config["proxy"] = proxy_url
        exchange = ccxt.binance(exchange_config)
        rows = exchange.fetch_ohlcv(
            _normalize_binance_symbol(symbol),
            timeframe=_map_binance_timeframe(timeframe),
            limit=max(20, int(limit or 200)),
        )
        out: List[Dict] = []
        for row in rows or []:
            try:
                out.append(
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            except Exception:
                continue
        return out
    except Exception:
        return []


async def _fetch_binance_ccxt_async(symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
    """Async CCXT adapter using ccxt.async_support with optional proxy support.

    Falls back to an empty list on import or runtime error so callers can try other providers.
    """
    try:
        import ccxt.async_support as ccxt_async  # type: ignore
    except Exception:
        return []

    try:
        proxy_url = (
            (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip()
            or proxy_manager.get_proxy_sync()
        )
        exchange_config: dict = {
            "enableRateLimit": True,
            "timeout": 2500,
        }
        if proxy_url:
            exchange_config["proxies"] = {"http": proxy_url, "https": proxy_url}
            exchange_config["proxy"] = proxy_url

        exchange = ccxt_async.binance(exchange_config)
        try:
            rows = await exchange.fetch_ohlcv(
                _normalize_binance_symbol(symbol),
                timeframe=_map_binance_timeframe(timeframe),
                limit=max(20, int(limit or 200)),
            )
        finally:
            try:
                await exchange.close()
            except Exception:
                pass

        out: List[Dict] = []
        for row in rows or []:
            try:
                out.append(
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            except Exception:
                continue
        return out
    except Exception:
        return []


def fetch_binance_ccxt_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
    async def _call() -> List[Dict]:
        # Prefer async ccxt when available and running inside an event loop.
        try:
            res = await asyncio.wait_for(_fetch_binance_ccxt_async(symbol, timeframe, limit), timeout=2.5)
            if res:
                return res
        except Exception:
            pass
        # Fallback to thread-executed sync adapter
        try:
            return await asyncio.wait_for(asyncio.to_thread(_fetch_binance_ccxt_sync, symbol, timeframe, limit), timeout=2.5)
        except Exception:
            return []

    try:
        res = run_sync(_call())
        if res:
            _set_candles_cache(symbol, timeframe, res)
        return res
    except Exception:
        return []


# ============================================================================
# POLYGON.IO - Premium multi-asset data (stocks, FX, crypto)
# ============================================================================

def fetch_polygon_candles(symbol: str, timeframe: str, asset_type: str = "stocks") -> List[Dict]:
    """
    Fetch OHLCV from Polygon.io.
    
    Args:
        symbol: Ticker (e.g., "AAPL", "EUR/USD", "X:BTCUSD")
        timeframe: "5m", "15m", "1h", "4h", "1d"
        asset_type: "stocks", "forex", "crypto"
    
    Returns:
        List of candle dicts with timestamp, open, high, low, close, volume
    """
    api_key = os.getenv("POLYGON_API_KEY", "").strip()
    if not api_key or _is_cooldown_active("polygon"):
        return []
    
    # Map timeframe to Polygon format
    tf_map = {
        "5m": ("5", "minute"),
        "15m": ("15", "minute"),
        "1h": ("1", "hour"),
        "4h": ("4", "hour"),
        "1d": ("1", "day"),
    }
    multiplier, timespan = tf_map.get(timeframe, ("1", "hour"))
    
    # Prefix symbol for asset type
    if asset_type == "forex":
        if "/" not in symbol:
            symbol = f"C:{symbol}"  # Polygon forex format: C:EURUSD
    elif asset_type == "crypto":
        if ":" not in symbol:
            symbol = f"X:BTC{symbol.replace('USDT', 'USD')}"  # X:BTCUSD format
    
    # Date range: last 200 periods
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=200 if timespan == "day" else 30)
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 200,
        "apiKey": api_key,
    }
    
    _rate_limit("polygon", _env_float("POLYGON_MIN_SECONDS_BETWEEN_CALLS", 12.0))
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json() if resp.ok else {}
        
        if not resp.ok:
            logger.warning(f"[polygon] fetch_failed symbol={symbol} status={resp.status_code}")
            _maybe_apply_rate_limit_cooldown("polygon", status_code=resp.status_code)
            return []
        
        results = data.get("results", [])
        if not results:
            return []
        
        candles = []
        for bar in results:
            try:
                candles.append({
                    "timestamp": int(bar["t"]),
                    "open": float(bar["o"]),
                    "high": float(bar["h"]),
                    "low": float(bar["l"]),
                    "close": float(bar["c"]),
                    "volume": float(bar.get("v", 0)),
                })
            except Exception:
                continue
        
        logger.info(f"[polygon] fetched symbol={symbol} tf={timeframe} candles={len(candles)}")
        _set_candles_cache(symbol, timeframe, candles)
        return candles
    
    except Exception as e:
        logger.error(f"[polygon] error symbol={symbol} err={e}")
        return []


# ============================================================================
# TWELVE DATA - Multi-asset with generous free tier
# ============================================================================

def fetch_twelvedata_candles(symbol: str, timeframe: str, asset_type: str = "stocks") -> List[Dict]:
    """Fetch OHLCV from Twelve Data API."""
    api_key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not api_key or _is_cooldown_active("twelvedata"):
        return []
    
    # Map timeframe
    tf_map = {
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1day",
    }
    interval = tf_map.get(timeframe, "1h")
    
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": 200,
        "apikey": api_key,
    }
    
    _rate_limit("twelvedata", _env_float("TWELVEDATA_MIN_SECONDS_BETWEEN_CALLS", 1.0))
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json() if resp.ok else {}
        
        if not resp.ok or data.get("status") == "error":
            logger.warning(f"[twelvedata] fetch_failed symbol={symbol} msg={data.get('message', '')}")
            _maybe_apply_rate_limit_cooldown(
                "twelvedata",
                status_code=resp.status_code,
                message=str(data.get("message", "")),
            )
            return []
        
        values = data.get("values", [])
        if not values:
            return []

        candles = []
        for bar in values:
            try:
                # Twelve Data returns datetime string
                dt = datetime.fromisoformat(bar["datetime"].replace("Z", ""))
                candles.append({
                    "timestamp": int(dt.timestamp() * 1000),
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": float(bar.get("volume", 0)),
                })
            except Exception:
                continue

        logger.info(f"[twelvedata] fetched symbol={symbol} tf={timeframe} candles={len(candles)}")
        _set_candles_cache(symbol, timeframe, candles)
        return candles
    
    except Exception as e:
        logger.error(f"[twelvedata] error symbol={symbol} err={e}")
        return []


# ============================================================================
# YAHOO FINANCE - Free, no API key needed
# ============================================================================

def fetch_yahoo_candles(symbol: str, timeframe: str) -> List[Dict]:
    """Fetch OHLCV from Yahoo Finance using yfinance library."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("[yahoo] yfinance not installed")
        return []
    
    if _is_cooldown_active("yahoo"):
        return []

    # Normalize symbols for Yahoo
    # - FX: EURUSD / EUR-USD -> EURUSD=X
    # - Crypto: BTCUSDT -> BTC-USD
    # - Commodities: XAUUSD -> GC=F, XAGUSD -> SI=F, WTI/WTIUSD -> CL=F
    try:
        s = str(symbol or "").upper().strip().replace("/", "").replace("_", "").replace("-", "")
        if s in {"XAUUSD", "GOLD"}:
            symbol = "GC=F"
        elif s in {"XAGUSD", "SILVER"}:
            symbol = "SI=F"
        elif s in {"WTI", "WTIUSD", "CRUDEOIL", "USOIL"}:
            symbol = "CL=F"
        elif s.endswith("USDT") and len(s) > 4:
            symbol = f"{s[:-4]}-USD"
        elif len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
            # EURUSD, GBPUSD etc
            symbol = f"{s}=X"
    except Exception:
        pass
    
    # Map timeframe to yfinance intervals
    tf_map = {
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "1h",  # Yahoo doesn't have 4h, we'll use 1h
        "1d": "1d",
    }
    interval = tf_map.get(timeframe, "1h")
    period_map = {
        "5m": "5d",
        "15m": "5d",
        "1h": "1mo",
        "4h": "3mo",
        "1d": "1y",
    }
    period = period_map.get(timeframe, "1mo")
    
    _rate_limit("yahoo", 0.5)  # Yahoo is pretty lenient
    
    def _fetch_history() -> "pd.DataFrame":
        ticker = yf.Ticker(symbol)
        return ticker.history(period=period, interval=interval)

    async def _fetch_with_timeout() -> "pd.DataFrame":
        timeout_s = float(os.getenv("YFINANCE_TIMEOUT_SECONDS", "6") or 6)
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_history),
            timeout=max(1.0, timeout_s),
        )

    try:
        hist = run_sync(_fetch_with_timeout())
        
        if hist.empty:
            return []
        
        candles = []
        for idx, row in hist.iterrows():
            try:
                candles.append({
                    "timestamp": int(idx.timestamp() * 1000),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume", 0)),
                })
            except Exception:
                continue
        
        logger.info(f"[yahoo] fetched symbol={symbol} tf={timeframe} candles={len(candles)}")
        _set_candles_cache(symbol, timeframe, candles)
        return candles
    
    except asyncio.TimeoutError:
        logger.warning(f"[yahoo] timeout symbol={symbol} tf={timeframe}")
        _set_cooldown("yahoo", 60.0)
        return []
    except Exception as e:
        logger.error(f"[yahoo] error symbol={symbol} err={e}")
        if "429" in str(e):
            _set_cooldown("yahoo", 60.0)
        return []


# ============================================================================
# OANDA - Bank-grade FX data (demo account = free)
# ============================================================================

def fetch_oanda_candles(instrument: str, timeframe: str) -> List[Dict]:
    """
    Fetch FX candles from OANDA API.
    
    Args:
        instrument: FX pair in format "EUR_USD" (OANDA uses underscore)
        timeframe: "5m", "15m", "1h", "4h", "1d"
    """
    api_key = os.getenv("OANDA_API_KEY", "").strip()
    account_id = os.getenv("OANDA_ACCOUNT_ID", "").strip()
    practice = os.getenv("OANDA_PRACTICE", "true").lower() == "true"
    
    if not api_key or _is_cooldown_active("oanda"):
        return []
    
    # Convert symbol format: EURUSD -> EUR_USD
    if "_" not in instrument and len(instrument) == 6:
        instrument = f"{instrument[:3]}_{instrument[3:]}"
    
    # Map timeframe to OANDA granularity
    tf_map = {
        "5m": "M5",
        "15m": "M15",
        "1h": "H1",
        "4h": "H4",
        "1d": "D",
    }
    granularity = tf_map.get(timeframe, "H1")
    
    base_url = "https://api-fxpractice.oanda.com" if practice else "https://api-fxtrade.oanda.com"
    url = f"{base_url}/v3/instruments/{instrument}/candles"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    params = {
        "count": 200,
        "granularity": granularity,
        "price": "M",  # Midpoint prices
    }
    
    _rate_limit("oanda", 0.5)
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json() if resp.ok else {}
        
        if not resp.ok:
            logger.warning(f"[oanda] fetch_failed instrument={instrument} status={resp.status_code}")
            if resp.status_code == 429:
                _set_cooldown("oanda", 60.0)
            return []
        
        candles_data = data.get("candles", [])
        if not candles_data:
            return []
        
        candles = []
        for bar in candles_data:
            try:
                if not bar.get("complete"):
                    continue  # Skip incomplete candles
                
                dt = datetime.fromisoformat(bar["time"].replace("Z", "+00:00"))
                mid = bar["mid"]
                candles.append({
                    "timestamp": int(dt.timestamp() * 1000),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": float(bar.get("volume", 0)),
                })
            except Exception:
                continue
        
        logger.info(f"[oanda] fetched instrument={instrument} tf={timeframe} candles={len(candles)}")
        _set_candles_cache(instrument, timeframe, candles)
        return candles
    
    except Exception as e:
        logger.error(f"[oanda] error instrument={instrument} err={e}")
        return []


# ============================================================================
# TRADINGVIEW - Fetch OHLCV data (in addition to technical summary)
# ============================================================================

def fetch_tradingview_candles(symbol: str, timeframe: str, exchange: str = "BINANCE") -> List[Dict]:
    """
    Fetch OHLCV candles from TradingView (requires web scraping or unofficial API).
    Note: TradingView doesn't have an official OHLCV API, so this uses tradingview-ta
    which only provides technical analysis summary. For actual candles, consider
    using tradingview-scraper or similar libraries.
    
    For now, this is a placeholder. Real implementation would need:
    - tradingview-scraper library or similar
    - Or use TradingView's chart data API (unofficial)
    """
    if not _env_bool("TRADINGVIEW_OHLCV_ENABLED", False):
        return []
    logger.warning("[tradingview] OHLCV fetching not yet implemented - use other providers")
    return []


# ============================================================================
# COINGECKO - Free crypto OHLCV (no API key required for basic use)
# ============================================================================

def fetch_coingecko_candles(symbol: str, timeframe: str) -> List[Dict]:
    """Fetch OHLCV from CoinGecko free API.

    symbol: canonical crypto symbol like "BTCUSDT" or CoinGecko ID like "bitcoin".
    timeframe: "1h", "4h", "1d" (CoinGecko has limited granularity).
    """
    try:
        from services.asset_mapper import map_symbol, classify_asset
        cg_id = map_symbol(symbol.upper(), "coingecko")
        if not cg_id:
            # Fall back to lower-case base
            cg_id = symbol.upper().replace("USDT", "").replace("USDC", "").lower()
    except Exception:
        cg_id = symbol.lower().replace("usdt", "").replace("usdc", "")

    if _is_cooldown_active("coingecko"):
        return []

    # CoinGecko /coins/{id}/ohlc: days param
    days_map = {"5m": 1, "15m": 1, "1h": 7, "4h": 30, "1d": 365}
    days = days_map.get(timeframe, 7)

    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
    params = {"vs_currency": "usd", "days": days}
    api_key = os.getenv("COINGECKO_API_KEY", "").strip()
    if api_key:
        params["x_cg_pro_api_key"] = api_key

    _rate_limit("coingecko", 1.5)

    try:
        resp = requests.get(url, params=params, timeout=15)
        if not resp.ok:
            if resp.status_code == 429:
                _set_cooldown("coingecko", 60.0)
            return []
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        candles = []
        for row in rows:
            try:
                ts, o, h, l, c = row
                candles.append({
                    "timestamp": int(ts),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": 0.0,
                })
            except Exception:
                continue
        logger.info("[coingecko] fetched id=%s tf=%s candles=%d", cg_id, timeframe, len(candles))
        if candles:
            _set_candles_cache(symbol, timeframe, candles)
        return candles
    except Exception as exc:
        logger.error("[coingecko] error id=%s err=%s", cg_id, exc)
        return []


# ============================================================================
# ALPHA VANTAGE - Traditional assets (stocks, FX)
# ============================================================================

def fetch_alphavantage_candles(symbol: str, timeframe: str) -> List[Dict]:
    """Fetch OHLCV from AlphaVantage."""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key or _is_cooldown_active("alphavantage"):
        return []

    try:
        from services.asset_mapper import classify_asset
        cls = classify_asset(symbol)
    except Exception:
        cls = "stock"

    tf_map = {"5m": "5min", "15m": "15min", "1h": "60min", "4h": "60min", "1d": "daily"}
    interval = tf_map.get(timeframe, "60min")
    _rate_limit("alphavantage", float(os.getenv("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", "20")))

    try:
        if cls == "forex":
            fn = "FX_INTRADAY" if timeframe != "1d" else "FX_DAILY"
            base, quote = (symbol[:3], symbol[3:]) if len(symbol) == 6 else (symbol, "USD")
            params: Dict = {"function": fn, "from_symbol": base, "to_symbol": quote,
                            "interval": interval, "outputsize": "full", "apikey": api_key}
        else:
            fn = "TIME_SERIES_INTRADAY" if timeframe != "1d" else "TIME_SERIES_DAILY"
            params = {"function": fn, "symbol": symbol, "interval": interval,
                      "outputsize": "full", "apikey": api_key}

        resp = requests.get("https://www.alphavantage.co/query", params=params, timeout=20)
        if not resp.ok:
            return []
        data = resp.json()
        # Find the time series key
        ts_key = next((k for k in data if "Time Series" in k), None)
        if not ts_key:
            if "Note" in data or "Information" in data:
                _set_cooldown("alphavantage", 60.0)
            return []
        ts = data[ts_key]
        candles = []
        for dt_str, bar in ts.items():
            try:
                dt = datetime.fromisoformat(dt_str)
                candles.append({
                    "timestamp": int(dt.timestamp() * 1000),
                    "open": float(bar.get("1. open") or bar.get("1a. open (USD)", 0)),
                    "high": float(bar.get("2. high") or bar.get("2a. high (USD)", 0)),
                    "low": float(bar.get("3. low") or bar.get("3a. low (USD)", 0)),
                    "close": float(bar.get("4. close") or bar.get("4a. close (USD)", 0)),
                    "volume": float(bar.get("5. volume", 0) or 0),
                })
            except Exception:
                continue
        candles.sort(key=lambda c: c["timestamp"])
        logger.info("[alphavantage] fetched symbol=%s tf=%s candles=%d", symbol, timeframe, len(candles))
        if candles:
            _set_candles_cache(symbol, timeframe, candles)
        return candles
    except Exception as exc:
        logger.error("[alphavantage] error symbol=%s: %s", symbol, exc)
        return []


# ============================================================================
# WATERFALL FETCHER - Unified entry point with provider fallbacks
# ============================================================================

def fetch_candles_waterfall(symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
    """Fetch OHLCV with automatic provider waterfall.

    Crypto:      Yahoo Finance -> Binance -> CoinGecko
    Forex:       Yahoo Finance -> OANDA -> Twelve Data -> Polygon
    Commodity:   Yahoo Finance -> AlphaVantage -> Twelve Data
    Stock:       Yahoo Finance -> AlphaVantage -> Polygon -> Twelve Data
    MT5 (if configured) is tried first for all asset classes when
    META_API_TOKEN is set (via the async mt5_client; sync fallback skips it).
    """
    # Keep a minimal, import-safe fallback waterfall that prefers the CCXT path.
    # Heuristic: treat USDT/USD tickers as crypto; forex pairs contain '/'
    sym = (symbol or "").upper()
    is_crypto_sym = sym.endswith("USDT") or sym.endswith("USD") or sym.endswith("BTC")
    is_forex_sym = "/" in symbol or "." in symbol and len(symbol) <= 7

    # 1) Prefer CCXT Binance for crypto-like symbols
    try:
        if is_crypto_sym:
            result = fetch_binance_ccxt_candles(symbol, timeframe, limit=limit)
            if result and len(result) >= 1:
                return result[-limit:]
    except Exception:
        pass

    # 2) CoinGecko market chart fallback for crypto
    try:
        if is_crypto_sym:
            cg = fetch_coingecko_market_chart(symbol, days=7)
            if cg and len(cg) >= 1:
                return cg[-limit:]
    except Exception:
        pass

    # 3) AlphaVantage for stocks/forex if configured
    try:
        av_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
        if av_key:
            av = fetch_alphavantage_candles(symbol, timeframe)
            if av and len(av) >= 1:
                return av[-limit:]
    except Exception:
        pass

    # 4) Polygon/TwelveData/others are already implemented above; try a lightweight Binance CCXT again as last resort
    try:
        result = fetch_binance_ccxt_candles(symbol, timeframe, limit=limit)
        if result and len(result) >= 1:
            return result[-limit:]
    except Exception:
        pass

    return []
