import os
import time
from datetime import datetime

import requests

from .indicators import calculate_indicators


_ALPHA_LAST_CALL_TS = 0.0
_BINANCE_BLOCKED_REASON: str | None = None


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
    """Fetch crypto candles from Binance public REST API.

    This reads *real* chart candles (no demo/synthetic generation) and avoids
    requiring `ccxt`.
    """

    tf_map = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get((timeframe or "").strip(), "1h")

    sym = (asset or "").upper().strip()
    # Expect Binance symbols like BTCUSDT; allow BTC/USD style too.
    sym = sym.replace("/", "").replace("-", "")
    if sym.endswith("USD") and not sym.endswith("USDT"):
        sym = sym[:-3] + "USDT"

    if not sym or len(sym) < 6:
        return []

    def _cryptocompare_candles(symbol_rest: str, tf: str) -> list[dict]:
        # CryptoCompare expects fsym/tsym (base/quote). We try multiple quote
        # currencies because some assets don't have a USDT market.
        base_raw = symbol_rest
        preferred_quote = "USDT"
        for q in ("USDT", "USDC", "BUSD", "USD"):
            if base_raw.endswith(q) and len(base_raw) > len(q):
                base_raw = base_raw[: -len(q)]
                preferred_quote = q
                break
        if not base_raw:
            return []

        tf = (tf or "").strip()
        # Map timeframe to endpoint + aggregate
        if tf in {"5m", "15m"}:
            endpoint = "histominute"
            aggregate = 5 if tf == "5m" else 15
        elif tf in {"1h", "4h"}:
            endpoint = "histohour"
            aggregate = 1 if tf == "1h" else 4
        else:
            endpoint = "histoday"
            aggregate = 1

        url_cc = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"

        headers = {}
        api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
        if api_key:
            headers["authorization"] = f"Apikey {api_key}"

        def _fetch_for_quote(tsym: str) -> list[dict]:
            params_cc = {
                "fsym": base_raw,
                "tsym": tsym,
                "limit": 200,
                "aggregate": aggregate,
            }

            resp = requests.get(url_cc, params=params_cc, headers=headers, timeout=12)
            payload = resp.json() if resp.ok else {}
            if not resp.ok:
                return []
            if str(payload.get("Response") or "").lower() != "success":
                return []

            data = (((payload.get("Data") or {}) or {}).get("Data") or [])
            if not isinstance(data, list) or not data:
                return []

            out: list[dict] = []
            for row in data:
                try:
                    ts_ms = int(row.get("time")) * 1000
                    out.append(
                        {
                            "timestamp": ts_ms,
                            "open": float(row.get("open")),
                            "high": float(row.get("high")),
                            "low": float(row.get("low")),
                            "close": float(row.get("close")),
                            "volume": float(row.get("volumefrom") or 0.0),
                        }
                    )
                except Exception:
                    continue
            return out

        tried: list[str] = []
        for tsym in (preferred_quote, "USDT", "USD", "USDC", "BUSD"):
            tsym = (tsym or "").upper().strip()
            if not tsym or tsym in tried:
                continue
            tried.append(tsym)
            out = _fetch_for_quote(tsym)
            if out:
                return out
        return []

    # Allow explicit provider override
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
    if provider == "cryptocompare":
        candles = _cryptocompare_candles(sym, interval)
        return candles or []

    global _BINANCE_BLOCKED_REASON
    if _BINANCE_BLOCKED_REASON is not None:
        candles = _cryptocompare_candles(sym, interval)
        return candles or []

    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": interval, "limit": 200}
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=10)
            payload = resp.json() if resp.ok else None

            if not resp.ok:
                msg = None
                try:
                    if isinstance(payload, dict):
                        msg = str(payload.get("msg") or payload.get("message") or "")
                except Exception:
                    msg = None
                msg_l = (msg or "").lower()
                if resp.status_code in {451, 403} or "restricted location" in msg_l:
                    _BINANCE_BLOCKED_REASON = msg or f"HTTP {resp.status_code}"
                    print(
                        f"[WARN] Binance appears geo-blocked (HTTP {resp.status_code}). Falling back to CryptoCompare for candles.",
                        flush=True,
                    )
                    candles = _cryptocompare_candles(sym, interval)
                    return candles or []
                raise RuntimeError(f"Binance klines HTTP {resp.status_code}")

            if not isinstance(payload, list):
                # Binance errors come back as dicts
                msg = None
                try:
                    if isinstance(payload, dict):
                        msg = str(payload.get("msg") or payload.get("message") or "")
                except Exception:
                    msg = None
                msg_l = (msg or "").lower()
                if "restricted location" in msg_l:
                    _BINANCE_BLOCKED_REASON = msg
                    print(
                        "[WARN] Binance appears geo-blocked (restricted location). Falling back to CryptoCompare for candles.",
                        flush=True,
                    )
                    candles = _cryptocompare_candles(sym, interval)
                    return candles or []
                raise RuntimeError(f"Unexpected Binance klines payload: {payload}")

            candles = []
            for row in payload:
                # [ openTime, open, high, low, close, volume, closeTime, ... ]
                try:
                    candles.append(
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
            return candles
        except Exception as e:
            print(f"[WARN] Binance candle fetch failed for {sym} {interval} (attempt {attempt}/{max_retries}): {e}")
            time.sleep(1)

    # Final fallback
    candles = _cryptocompare_candles(sym, interval)
    return candles or []

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
