from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable

import yfinance as yf

from data.fetcher import fetch_market_data as fetch_market_data_rest
from db.market_cache import get_recent_candles
from db.session import get_session

logger = logging.getLogger(__name__)


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


def _convert_to_yfinance_symbol(asset: str) -> str:
    """Convert internal asset symbol to yfinance format."""
    asset = asset.upper().strip()
    
    # Crypto: BTCUSDT -> BTC-USD
    if asset.endswith("USDT"):
        base = asset[:-4]
        return f"{base}-USD"
    
    # FX: EURUSD -> EURUSD=X
    if len(asset) == 6 and asset[:3].isalpha() and asset[3:].isalpha():
        # Common FX pairs
        major_currencies = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
        if asset[:3] in major_currencies and asset[3:] in major_currencies:
            return f"{asset}=X"
    
    # Commodities
    commodity_map = {
        "XAUUSD": "GC=F",  # Gold
        "XAGUSD": "SI=F",  # Silver
        "WTIUSD": "CL=F",  # WTI Crude Oil
        "CRUDEOIL": "CL=F",  # Crude Oil
        "NATGAS": "NG=F",  # Natural Gas
    }
    if asset in commodity_map:
        return commodity_map[asset]
    
    # Stocks: AAPL -> AAPL (no change)
    return asset


def _fetch_via_yfinance(asset: str, timeframe: str, limit: int) -> list[dict]:
    """Fetch market data via yfinance.
    
    Args:
        asset: Internal asset symbol
        timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        limit: Number of candles to fetch
    
    Returns:
        List of candles with keys: open, high, low, close, volume, timestamp
    """
    try:
        # Convert symbol
        yf_symbol = _convert_to_yfinance_symbol(asset)
        
        # Map timeframe to yfinance interval
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "60m",  # yfinance doesn't support 4h, use 1h and aggregate
            "1d": "1d",
            "1w": "1wk",
        }
        interval = interval_map.get(timeframe, "1h")
        
        # Map timeframe to yfinance period
        period_map = {
            "1m": "1d",
            "5m": "5d",
            "15m": "5d",
            "1h": "30d",
            "4h": "60d",
            "1d": "365d",
            "1w": "2y",
        }
        period = period_map.get(timeframe, "30d")
        
        # Fetch data
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df is None or df.empty:
            logger.warning(f"yfinance returned no data for {yf_symbol} ({asset})")
            return []
        
        # Convert to list of dicts
        candles = []
        for idx, row in df.iterrows():
            try:
                # idx is a pandas Timestamp
                timestamp = int(idx.timestamp())
                candle = {
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]) if "Volume" in row else 0.0,
                    "timestamp": timestamp,
                }
                candles.append(candle)
            except Exception as e:
                logger.debug(f"Failed to parse yfinance row: {e}")
                continue
        
        # For 4h timeframe, aggregate 4x 1h candles
        if timeframe == "4h" and interval == "60m":
            aggregated = []
            i = 0
            while i + 3 < len(candles):
                chunk = candles[i:i+4]
                agg_candle = {
                    "open": chunk[0]["open"],
                    "high": max(c["high"] for c in chunk),
                    "low": min(c["low"] for c in chunk),
                    "close": chunk[-1]["close"],
                    "volume": sum(c["volume"] for c in chunk),
                    "timestamp": chunk[-1]["timestamp"],
                }
                aggregated.append(agg_candle)
                i += 4
            candles = aggregated
        
        # Limit to requested number of candles
        if len(candles) > limit:
            candles = candles[-limit:]
        
        logger.info(f"yfinance fetched {len(candles)} candles for {asset} ({yf_symbol}) {timeframe}")
        return candles
        
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {asset} {timeframe}: {e}")
        return []


def get_realtime_price(asset: str) -> float | None:
    """Get real-time price for an asset.
    
    Tries yfinance first, then Binance REST for crypto, then last candle close.
    
    Args:
        asset: Internal asset symbol
    
    Returns:
        Current price or None if unavailable
    """
    # Try yfinance
    try:
        yf_symbol = _convert_to_yfinance_symbol(asset)
        ticker = yf.Ticker(yf_symbol)
        price = ticker.fast_info.get('lastPrice')
        if price and price > 0:
            return float(price)
    except Exception as e:
        logger.debug(f"yfinance realtime price failed for {asset}: {e}")
    
    # Fallback to Binance REST for crypto
    if asset.upper().endswith("USDT") or asset.upper().endswith("USD"):
        try:
            import requests
            binance_symbol = asset.upper().replace("/", "").replace("-", "")
            if not binance_symbol.endswith("USDT"):
                binance_symbol = binance_symbol.replace("USD", "USDT")
            resp = requests.get(
                f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}",
                timeout=5
            )
            if resp.status_code == 200:
                price = float(resp.json()["price"])
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"Binance realtime price failed for {asset}: {e}")
    
    # No realtime price available
    return None


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
                    import time as _time
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
                        logger.info(f"[market_data] cache: asset={asset} tf={tf} candles_fetched={len(candles)}")
                    if candles and len(candles) >= want:
                        # Add data age calculation
                        import time as _time
                        if candles:
                            latest_ts = candles[-1].get("timestamp", 0)
                            data_age = int(_time.time() - latest_ts) if latest_ts > 0 else None
                        else:
                            data_age = None
                        
                        out[tf] = {
                            "candles": candles,
                            "source": "cache",
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
        
        # Add data age to REST responses
        import time as _time
        for tf, payload in (rest or {}).items():
            if isinstance(payload, dict):
                candles = payload.get("candles", [])
                if candles:
                    latest_ts = candles[-1].get("timestamp", 0)
                    data_age = int(_time.time() - latest_ts) if latest_ts > 0 else None
                    payload["data_age_seconds"] = data_age
                    payload.setdefault("source", "rest")
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
