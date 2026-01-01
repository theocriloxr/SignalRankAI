import os
import time
from datetime import datetime

import requests

from .indicators import calculate_indicators


_ALPHA_LAST_CALL_TS = 0.0


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _alphavantage_rate_limit() -> None:
    """Best-effort global rate limit for AlphaVantage.

    Free tier is very limited, so we default to ~4 calls/minute.
    Override via ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS.
    """
    global _ALPHA_LAST_CALL_TS
    min_seconds = max(0.0, _env_float("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", 15.0))
    if min_seconds <= 0:
        return
    now = time.monotonic()
    wait = (_ALPHA_LAST_CALL_TS + min_seconds) - now
    if wait > 0:
        time.sleep(wait)
    _ALPHA_LAST_CALL_TS = time.monotonic()

def fetch_market_data(asset, timeframes):
    data = {}
    for tf in timeframes:
        try:
            candles = get_candles(asset, tf)
            # Validate candles: must be non-empty and have 'close' key in first row
            if not candles or 'close' not in candles[0]:
                continue
            indicators = calculate_indicators(candles)
            data[tf] = {
                'candles': candles,
                'indicators': indicators
            }
        except Exception as e:
            print(f"[WARN] Skipping {asset} {tf} due to error: {e}")
            continue
    return data

def get_candles(asset, timeframe):
    if is_crypto(asset):
        return get_crypto_candles(asset, timeframe)
    else:
        return get_fx_candles(asset, timeframe)

def is_crypto(asset):
    a = (asset or "").upper().strip()
    # Treat Binance-style symbols as crypto by default (e.g., BTCUSDT, ETHUSDT).
    return a.endswith("USDT") or a.endswith("BUSD") or a.endswith("USDC")

def get_crypto_candles(asset, timeframe):
    import ccxt
    import time
    exchange = ccxt.binance()
    symbol = asset.replace('USD', '/USDT') if not asset.endswith('USDT') else asset.replace('USDT', '/USDT')
    tf_map = {'5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'}
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf_map.get(timeframe, '1h'), limit=100)
            candles = []
            for o in ohlcv:
                candles.append({'timestamp': o[0], 'open': o[1], 'high': o[2], 'low': o[3], 'close': o[4], 'volume': o[5]})
            return candles
        except Exception as e:
            print(f"Error fetching candles for {symbol} (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(2)
    print(f"Failed to fetch candles for {symbol} after {max_retries} attempts.")
    return []

def get_fx_candles(asset, timeframe):
    """Fetch FX candles from a real candle provider.

    This intentionally avoids synthetic OHLC generation.
    Requires ALPHAVANTAGE_API_KEY to be set.
    """
    api_key = (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()
    if not api_key:
        return []

    pair = (asset or "").upper().strip()
    if len(pair) < 6:
        return []
    from_symbol, to_symbol = pair[:3], pair[3:6]

    tf = (timeframe or "").strip()
    if tf in {"5m", "15m", "1h"}:
        interval = {"5m": "5min", "15m": "15min", "1h": "60min"}[tf]
        url = (
            "https://www.alphavantage.co/query"
            f"?function=FX_INTRADAY&from_symbol={from_symbol}&to_symbol={to_symbol}"
            f"&interval={interval}&outputsize=compact&apikey={api_key}"
        )
        _alphavantage_rate_limit()
        resp = requests.get(url, timeout=10)
        payload = resp.json() if resp.ok else {}
        # AlphaVantage sends throttle notices in-body with 200 OK
        if any(k in payload for k in ("Note", "Information", "Error Message")):
            return []
        key = f"Time Series FX ({interval})"
        series = payload.get(key) or {}
        candles = []
        for ts, row in sorted(series.items()):
            try:
                candles.append(
                    {
                        "timestamp": ts,
                        "open": float(row["1. open"]),
                        "high": float(row["2. high"]),
                        "low": float(row["3. low"]),
                        "close": float(row["4. close"]),
                        "volume": 0.0,
                    }
                )
            except Exception:
                continue

        # For 4h, aggregate from 60min bars.
        if tf == "1h":
            return candles
        return candles

    if tf in {"4h", "1d"}:
        # Use daily candles for now; 4h requires intraday aggregation.
        if tf == "4h":
            # Try to approximate 4h by aggregating 60min bars.
            url = (
                "https://www.alphavantage.co/query"
                f"?function=FX_INTRADAY&from_symbol={from_symbol}&to_symbol={to_symbol}"
                f"&interval=60min&outputsize=compact&apikey={api_key}"
            )
            _alphavantage_rate_limit()
            resp = requests.get(url, timeout=10)
            payload = resp.json() if resp.ok else {}
            if any(k in payload for k in ("Note", "Information", "Error Message")):
                return []
            series = payload.get("Time Series FX (60min)") or {}
            hourly = []
            for ts, row in sorted(series.items()):
                try:
                    hourly.append(
                        {
                            "timestamp": ts,
                            "open": float(row["1. open"]),
                            "high": float(row["2. high"]),
                            "low": float(row["3. low"]),
                            "close": float(row["4. close"]),
                            "volume": 0.0,
                        }
                    )
                except Exception:
                    continue
            if not hourly:
                return []

            # Group by 4-hour buckets based on timestamp hour.
            buckets: dict[str, list[dict]] = {}
            for bar in hourly:
                try:
                    dt = datetime.fromisoformat(str(bar["timestamp"]).replace("Z", ""))
                    bucket_hour = (dt.hour // 4) * 4
                    bucket_key = dt.replace(minute=0, second=0, microsecond=0, hour=bucket_hour).isoformat()
                except Exception:
                    bucket_key = str(bar["timestamp"]).split(":")[0]
                buckets.setdefault(bucket_key, []).append(bar)

            out = []
            for k in sorted(buckets.keys()):
                bars = buckets[k]
                if not bars:
                    continue
                o = bars[0]["open"]
                c = bars[-1]["close"]
                h = max(b["high"] for b in bars)
                l = min(b["low"] for b in bars)
                out.append({"timestamp": k, "open": o, "high": h, "low": l, "close": c, "volume": 0.0})
            return out

        # Daily
        url = (
            "https://www.alphavantage.co/query"
            f"?function=FX_DAILY&from_symbol={from_symbol}&to_symbol={to_symbol}"
            f"&outputsize=compact&apikey={api_key}"
        )
        _alphavantage_rate_limit()
        resp = requests.get(url, timeout=10)
        payload = resp.json() if resp.ok else {}
        if any(k in payload for k in ("Note", "Information", "Error Message")):
            return []
        series = payload.get("Time Series FX (Daily)") or {}
        candles = []
        for ts, row in sorted(series.items()):
            try:
                candles.append(
                    {
                        "timestamp": ts,
                        "open": float(row["1. open"]),
                        "high": float(row["2. high"]),
                        "low": float(row["3. low"]),
                        "close": float(row["4. close"]),
                        "volume": 0.0,
                    }
                )
            except Exception:
                continue
        return candles

    return []
