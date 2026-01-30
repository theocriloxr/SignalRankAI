"""
Multi-provider data fetching with automatic fallbacks.
Supports: Polygon.io, Twelve Data, Yahoo Finance, OANDA, TradingView.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Rate limiting state
_PROVIDER_LAST_CALL = {}
_PROVIDER_COOLDOWN = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _rate_limit(provider: str, min_seconds: float = 1.0) -> None:
    """Global rate limiter per provider."""
    global _PROVIDER_LAST_CALL
    if min_seconds <= 0:
        return
    last = _PROVIDER_LAST_CALL.get(provider, 0.0)
    now = time.monotonic()
    wait = (last + min_seconds) - now
    if wait > 0:
        time.sleep(wait)
    _PROVIDER_LAST_CALL[provider] = time.monotonic()


def _is_cooldown_active(provider: str) -> bool:
    """Check if provider is in cooldown due to rate limit."""
    global _PROVIDER_COOLDOWN
    cooldown_until = _PROVIDER_COOLDOWN.get(provider, 0.0)
    return time.monotonic() < cooldown_until


def _set_cooldown(provider: str, seconds: float) -> None:
    """Set provider cooldown."""
    global _PROVIDER_COOLDOWN
    _PROVIDER_COOLDOWN[provider] = time.monotonic() + seconds


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
            if resp.status_code == 429:
                _set_cooldown("polygon", 60.0)
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
            if "API rate limit" in str(data.get("message", "")):
                _set_cooldown("twelvedata", 60.0)
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
    
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        
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
        return candles
    
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
    logger.warning("[tradingview] OHLCV fetching not yet implemented - use other providers")
    return []
    
    # Future implementation could use:
    # from tradingview_ta import TA_Handler, Interval
    # But TA_Handler doesn't return OHLCV, only technical indicators
    # Would need tradingview-scraper or selenium-based solution
