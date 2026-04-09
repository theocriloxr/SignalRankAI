import threading
import time

# Provider health state (in-memory, per process)
_PROVIDER_HEALTH = {}
_PROVIDER_HEALTH_LOCK = threading.Lock()
_PROVIDER_FAIL_WINDOW = 600  # seconds to deprioritize after repeated failures
_PROVIDER_FAIL_THRESHOLD = 3

# Short-lived candle memoization to prevent N+1 duplicate provider calls when
# multiple strategies ask for the same symbol/timeframe in the same second.
_CANDLE_CACHE: dict[tuple[str, str], tuple[float, list]] = {}
_CANDLE_CACHE_LOCK = threading.Lock()
_CANDLE_KEY_LOCKS: dict[tuple[str, str], threading.Lock] = {}

# Outage tracking for automated alerts
_PROVIDER_OUTAGE_ALERTED = {}
_PROVIDER_OUTAGE_MINUTES = 10  # Alert if down for more than X minutes

def mark_provider_result(provider_name, ok):
    now = time.time()
    with _PROVIDER_HEALTH_LOCK:
        entry = _PROVIDER_HEALTH.setdefault(provider_name, {"failures": [], "last_success": 0})
        if ok:
            entry["last_success"] = now
            entry["failures"] = []
            # Reset outage alert state
            _PROVIDER_OUTAGE_ALERTED[provider_name] = False
        else:
            entry["failures"].append(now)
            # Keep only recent failures
            entry["failures"] = [t for t in entry["failures"] if now - t < _PROVIDER_FAIL_WINDOW]

def provider_is_healthy(provider_name):
    now = time.time()
    with _PROVIDER_HEALTH_LOCK:
        entry = _PROVIDER_HEALTH.get(provider_name)
        if not entry:
            return True
        if len(entry["failures"]) >= _PROVIDER_FAIL_THRESHOLD:
            # If last failure was recent and no recent success, mark unhealthy
            if now - entry["failures"][-1] < _PROVIDER_FAIL_WINDOW and (now - entry["last_success"] > _PROVIDER_FAIL_WINDOW):
                return False
        return True


def _get_candle_key_lock(key: tuple[str, str]) -> threading.Lock:
    with _CANDLE_CACHE_LOCK:
        lock = _CANDLE_KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CANDLE_KEY_LOCKS[key] = lock
        return lock


def _read_cached_candles(key: tuple[str, str], ttl_seconds: float) -> list | None:
    now = time.time()
    with _CANDLE_CACHE_LOCK:
        entry = _CANDLE_CACHE.get(key)
        if not entry:
            return None
        ts, candles = entry
        if (now - ts) > max(0.0, float(ttl_seconds)):
            _CANDLE_CACHE.pop(key, None)
            return None
        # Return a shallow structural copy to avoid accidental mutation by callers.
        return [dict(c) if isinstance(c, dict) else c for c in (candles or [])]


def _write_cached_candles(key: tuple[str, str], candles: list) -> None:
    with _CANDLE_CACHE_LOCK:
        _CANDLE_CACHE[key] = (time.time(), list(candles or []))


# Return list of (provider_name, minutes_down) for providers down > threshold
def get_unhealthy_providers(min_minutes=None):
    now = time.time()
    min_minutes = min_minutes or _PROVIDER_OUTAGE_MINUTES
    unhealthy = []
    with _PROVIDER_HEALTH_LOCK:
        for name, entry in _PROVIDER_HEALTH.items():
            if len(entry["failures"]) >= _PROVIDER_FAIL_THRESHOLD:
                last_success = entry["last_success"]
                if last_success == 0:
                    # Provider was never successfully polled in this process; skip
                    continue
                down_for = (now - last_success) / 60.0
                if down_for >= min_minutes:
                    unhealthy.append((name, down_for))
    return unhealthy
import random
def retry_with_backoff(fetch_func, max_retries=3, base_timeout=10, max_timeout=60, jitter=0.2):
    """Retry a fetch function with exponential backoff and jitter."""
    for attempt in range(max_retries):
        timeout = min(base_timeout * (2 ** attempt), max_timeout)
        # Add jitter
        timeout = timeout * (1 + random.uniform(-jitter, jitter))
        try:
            return fetch_func(timeout=timeout)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(timeout)
    return None
import os
import time
import logging
from datetime import datetime

import requests
import asyncio
from core.circuit_breaker import provider_breaker

# Import market hours module for holiday checks
try:
    from data.market_hours import is_stock_holiday, is_commodity_holiday, is_fx_low_liquidity
except ImportError:
    # Fallback if module doesn't exist yet
    def is_stock_holiday(now_utc=None):
        return None
    def is_commodity_holiday(now_utc=None):
        return None
    def is_fx_low_liquidity(now_utc=None):
        return False

# Async retry helper (uses shared httpx client when available)
try:
    from utils.httpx_client import retry_async as retry_async_httpx
except Exception:
    # Fallback: simple async wrapper around sync retry (keeps compatibility)
    async def retry_async_httpx(fn, retries: int = 3, backoff: float = 1.0, *args, **kwargs):
        last_exc = None
        for attempt in range(retries):
            try:
                # If fn is coroutine function, await it, else run in thread
                res = fn(*args, **kwargs)
                if asyncio.iscoroutine(res):
                    return await res
                return await asyncio.to_thread(lambda: res)
            except Exception as exc:
                last_exc = exc
                wait = backoff * (2 ** attempt)
                await asyncio.sleep(wait)
        raise last_exc

from .indicators import calculate_indicators

logger = logging.getLogger(__name__)


_ALPHA_LAST_CALL_TS = 0.0
_ALPHA_COOLDOWN_UNTIL = 0.0
_BINANCE_BLOCKED_REASON: str | None = None


def is_binance_blocked() -> bool:
    return _BINANCE_BLOCKED_REASON is not None


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
    min_seconds = max(0.0, _env_float("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", 20.0))
    if min_seconds <= 0:
        return
    now = time.monotonic()
    wait = (_ALPHA_LAST_CALL_TS + min_seconds) - now
    if wait > 0:
        time.sleep(wait)
    _ALPHA_LAST_CALL_TS = time.monotonic()

def fetch_market_data(asset, timeframes):
    """Fetch live market data with validation and freshness checks."""
    data = {}
    for tf in timeframes:
        try:
            candles = get_candles(asset, tf)
            # Validate candles: must be non-empty and have required fields
            if not candles or not isinstance(candles, list) or len(candles) < 20:
                continue
            
            # Verify candle structure
            first = candles[0]
            required_keys = {'close', 'high', 'low', 'open', 'timestamp'}
            if not all(k in first for k in required_keys):
                continue
            
            # Check candle freshness - most recent candle should not be too old
            latest_candle = candles[-1]
            latest_timestamp = latest_candle.get('timestamp', 0)

            # Normalize timestamp to epoch seconds (accepts ms, s, or ISO string)
            def _to_epoch_seconds(ts_val):
                try:
                    if isinstance(ts_val, str):
                        _s = ts_val.strip()
                        if _s.isdigit():
                            ts_num = int(_s)
                            return ts_num / 1000.0 if ts_num > 1_000_000_000_000 else float(ts_num)
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(_s.replace('Z', '+00:00'))
                            return dt.timestamp()
                        except Exception:
                            return 0.0
                    if isinstance(ts_val, (int, float)):
                        ts_num = float(ts_val)
                        return ts_num / 1000.0 if ts_num > 1_000_000_000_000 else ts_num
                except Exception:
                    return 0.0
                return 0.0

            latest_ts_sec = _to_epoch_seconds(latest_timestamp)

            # Convert timeframe to seconds
            tf_seconds = _timeframe_to_seconds(tf)
            current_time = time.time()

            # Import candle staleness multiplier
            from core.tier_constants import CANDLE_STALENESS_MULTIPLIER

            # Candles should be at most N times the timeframe interval old
            max_age = tf_seconds * CANDLE_STALENESS_MULTIPLIER
            candle_age = (current_time - latest_ts_sec) if latest_ts_sec else float('inf')
            
            if candle_age > max_age:
                logger.warning(f"[fetcher] Candle data for {asset} {tf} is stale: {candle_age:.0f}s old (max: {max_age:.0f}s)")
                # Still use the data but log the warning
            
            # Calculate indicators from real candle data
            indicators = calculate_indicators(candles)
            if not indicators:
                continue  # Indicator calculation failed
            
            data[tf] = {
                'candles': candles,
                'indicators': indicators,
                'fetched_at': current_time,
                'latest_candle_timestamp': latest_ts_sec,
                'candle_age_seconds': candle_age
            }
        except Exception as e:
            print(f"[WARN] Skipping {asset} {tf} due to error: {e}")
            continue
    return data


def _timeframe_to_seconds(timeframe: str) -> int:
    """Convert timeframe string to seconds."""
    tf = timeframe.lower().strip()
    multipliers = {
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    
    # Extract number and unit (e.g., "5m" -> 5, "m")
    import re
    match = re.match(r'(\d+)([mhdw])', tf)
    if match:
        num, unit = match.groups()
        return int(num) * multipliers.get(unit, 60)
    
    # Default mappings for common timeframes
    defaults = {
        '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
        '1h': 3600, '4h': 14400, '1d': 86400
    }
    return defaults.get(tf, 300)

def get_candles(asset, timeframe):
    """
    Unified candle fetcher with multi-provider fallback.
    
    Provider Priority:
    - Crypto: Binance → Bybit → **CryptoCompare** (works in Nigeria when Binance blocked)
    - FX: AlphaVantage → Yahoo → Polygon → Twelve Data (OANDA disabled for Nigeria)
    - Stocks: Yahoo → Polygon → Twelve Data
    """
    try:
        _asset_norm = str(asset or "").upper().strip()
        _tf_norm = str(timeframe or "").lower().strip()
        _cache_key = (_asset_norm, _tf_norm)
        _cache_ttl = float((os.getenv("CANDLE_REQUEST_CACHE_TTL_SECONDS") or "1.5").strip())

        # Fast path: short-lived cache hit.
        _cached = _read_cached_candles(_cache_key, _cache_ttl)
        if _cached is not None:
            return _cached

        # Coalesce concurrent callers for the same key.
        _key_lock = _get_candle_key_lock(_cache_key)
        with _key_lock:
            # Re-check after acquiring key lock.
            _cached = _read_cached_candles(_cache_key, _cache_ttl)
            if _cached is not None:
                return _cached

            asset_type = get_asset_type(asset)

            # Enable multi-provider via env var
            use_multi_provider = os.getenv("USE_MULTI_PROVIDER_DATA", "true").lower() == "true"

            if not use_multi_provider:
                # Legacy single-provider mode
                if asset_type == "crypto":
                    candles = get_crypto_candles(asset, timeframe)
                elif asset_type == "fx":
                    candles = get_fx_candles(asset, timeframe)
                else:
                    candles = get_stock_candles(asset, timeframe)
                _write_cached_candles(_cache_key, candles or [])
                return candles or []

            # Multi-provider mode with fallbacks
            if asset_type == "crypto":
                candles = _fetch_crypto_multi_provider(asset, timeframe)
            elif asset_type == "fx":
                candles = _fetch_fx_multi_provider(asset, timeframe)
            else:  # stock
                candles = _fetch_stock_multi_provider(asset, timeframe)

            _write_cached_candles(_cache_key, candles or [])
            return candles or []
    except Exception:
        logger.exception("get_candles failed for %s %s", asset, timeframe)
        return []


def _fetch_crypto_multi_provider(asset, timeframe):
    """Try multiple crypto providers in order.
    
    NOTE: For Nigeria (Binance blocked):
    - Binance/Bybit → Yahoo Finance (free, works worldwide) → CryptoCompare
    - Yahoo requires symbol conversion: BTCUSDT → BTC-USD
    """
    # Build provider list from connector registry (prefer connectors)
    from data.connector_registry import get_providers_for_asset

    provs = get_providers_for_asset("crypto")
    providers = []
    # Wrap provider callables to accept timeout kw param used by retry_with_backoff
    for name, fn in provs:
        providers.append((name, lambda timeout=10, _fn=fn: _fn(asset, timeframe, timeout=timeout)))
    healthy_providers = [p for p in providers if provider_is_healthy(p[0])]
    unhealthy_providers = [p for p in providers if not provider_is_healthy(p[0])]
    for provider_name, fetch_func in healthy_providers + unhealthy_providers:
        try:
            candles = retry_with_backoff(fetch_func, max_retries=3, base_timeout=10, max_timeout=60)
            if candles and len(candles) >= 20:
                mark_provider_result(provider_name, True)
                logger.info(f"[data] crypto_provider={provider_name} symbol={asset} tf={timeframe} candles={len(candles)}")
                return candles
            else:
                mark_provider_result(provider_name, False)
        except Exception as e:
            mark_provider_result(provider_name, False)
            logger.warning(f"[data] crypto_provider={provider_name} symbol={asset} failed: {e}")
            continue
    logger.warning(f"[data] crypto_fetched=none symbol={asset} tf={timeframe} (all providers failed)")
    return []


def _fetch_fx_multi_provider(asset, timeframe):
    """Try multiple FX providers in order."""
    from .providers import fetch_oanda_candles, fetch_polygon_candles, fetch_twelvedata_candles, fetch_yahoo_candles
    
    # Convert to formats needed by different providers
    oanda_format = asset.replace("/", "_").replace("-", "_").upper()
    yahoo_format = asset.replace("_", "").replace("-", "")
    if "/" not in yahoo_format and len(yahoo_format) == 6:
        yahoo_format = f"{yahoo_format[:3]}{yahoo_format[3:]}=X"  # Yahoo FX format: EURUSD=X
    
    alpha_enabled = os.getenv("ALPHAVANTAGE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    providers = [
        ("oanda", lambda timeout=10: fetch_oanda_candles(oanda_format, timeframe)),
        ("yahoo", lambda timeout=10: fetch_yahoo_candles(yahoo_format, timeframe)),
        ("polygon", lambda timeout=10: fetch_polygon_candles(asset, timeframe, "forex")),
        ("twelvedata", lambda timeout=10: fetch_twelvedata_candles(asset, timeframe, "forex")),
    ]
    if alpha_enabled:
        providers.append(("alphavantage", lambda timeout=10: get_fx_candles(asset, timeframe)))
    healthy_providers = [p for p in providers if provider_is_healthy(p[0])]
    unhealthy_providers = [p for p in providers if not provider_is_healthy(p[0])]
    for provider_name, fetch_func in healthy_providers + unhealthy_providers:
        try:
            candles = retry_with_backoff(fetch_func, max_retries=3, base_timeout=10, max_timeout=60)
            if candles and len(candles) >= 20:
                mark_provider_result(provider_name, True)
                logger.info(f"[data] fx_provider={provider_name} symbol={asset} tf={timeframe} candles={len(candles)}")
                return candles
            else:
                mark_provider_result(provider_name, False)
        except Exception as e:
            mark_provider_result(provider_name, False)
            logger.warning(f"[data] fx_provider={provider_name} symbol={asset} failed: {e}")
            continue
    logger.warning(f"[data] fx_fetched=none symbol={asset} tf={timeframe} (all providers failed)")
    return []


def _fetch_stock_multi_provider(asset, timeframe):
    """Try multiple stock providers in order."""
    from .providers import fetch_yahoo_candles, fetch_polygon_candles, fetch_twelvedata_candles
    
    from data.connector_registry import get_providers_for_asset

    provs = get_providers_for_asset("stock")
    providers = []
    for name, fn in provs:
        providers.append((name, lambda timeout=10, _fn=fn: _fn(asset, timeframe, timeout=timeout)))
    healthy_providers = [p for p in providers if provider_is_healthy(p[0])]
    unhealthy_providers = [p for p in providers if not provider_is_healthy(p[0])]
    for provider_name, fetch_func in healthy_providers + unhealthy_providers:
        try:
            candles = retry_with_backoff(fetch_func, max_retries=3, base_timeout=10, max_timeout=60)
            if candles and len(candles) >= 20:
                mark_provider_result(provider_name, True)
                logger.info(f"[data] stock_provider={provider_name} symbol={asset} tf={timeframe} candles={len(candles)}")
                return candles
            else:
                mark_provider_result(provider_name, False)
        except Exception as e:
            mark_provider_result(provider_name, False)
            logger.warning(f"[data] stock_provider={provider_name} symbol={asset} failed: {e}")
            continue
    logger.warning(f"[data] stock_fetched=none symbol={asset} tf={timeframe} (all providers failed)")
    return []


def get_stock_candles(asset, timeframe):
    """Legacy single-provider stock fetcher - uses Yahoo as default."""
    from .providers import fetch_yahoo_candles
    return fetch_yahoo_candles(asset, timeframe)

def is_crypto(asset):
    a = (asset or "").upper().strip()
    # Treat Binance-style symbols as crypto by default (e.g., BTCUSDT, ETHUSDT).
    if a.endswith("USDT") or a.endswith("BUSD") or a.endswith("USDC"):
        return True

    # If it ends with plain USD, distinguish FX majors from crypto tickers.
    if a.endswith("USD"):
        base = a[:-3]
        fx_bases = {"EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD", "HKD", "SGD", "SEK", "NOK"}
        if base in fx_bases:
            return False  # FX pair like EURUSD
        # If base is longer than 4 chars, treat as crypto (e.g., DOGEUSD)
        return len(base) > 4

    return False


def is_fx(asset):
    """Check if asset is a forex pair."""
    a = (asset or "").upper().strip()
    
    # FX pairs are typically 6-7 characters: EURUSD, EUR/USD, EUR_USD
    clean = a.replace("/", "").replace("_", "").replace("-", "")
    
    if len(clean) == 6:
        base = clean[:3]
        quote = clean[3:]
        fx_currencies = {"EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD", "HKD", "SGD", "SEK", "NOK", "DKK", "PLN", "TRY", "MXN", "ZAR"}
        return base in fx_currencies and quote in fx_currencies
    
    return False


def is_stock(asset):
    """Check if asset is a stock ticker."""
    # If not crypto and not FX and not commodity, assume stock
    return not is_crypto(asset) and not is_fx(asset) and not is_commodity(asset)


def is_commodity(asset):
    """Check if asset is a commodity ticker (e.g., XAUUSD, XAGUSD, WTI, BRENT, etc.)."""
    a = (asset or "").upper().strip()
    # Common commodity codes (expand as needed)
    commodity_keywords = [
        "XAU", "XAG", "XPT", "XPD",  # Precious metals
        "WTI", "BRENT", "OIL", "NG",  # Energy
        "COPPER", "PLATINUM", "PALLADIUM", "SILVER", "GOLD"
    ]
    # Check for common commodity asset codes or names
    for kw in commodity_keywords:
        if kw in a:
            return True
    # Some brokers use codes like XAUUSD, XAGUSD, etc.
    if a.endswith("USD") and a[:3] in {"XAU", "XAG", "XPT", "XPD"}:
        return True
    return False


def get_asset_type(asset):
    """Determine asset type: 'crypto', 'fx', 'stock', or 'commodity'."""
    if is_crypto(asset):
        return "crypto"
    elif is_fx(asset):
        return "fx"
    elif is_commodity(asset):
        return "commodity"
    else:
        return "stock"


def market_closed_reason(asset, now_utc: datetime | None = None) -> str | None:
    """Return a human-readable reason if the asset's market is closed.

    - Crypto: 24/7, always open
    - FX: Closed over weekend; open Sunday 22:00 UTC → Friday 22:00 UTC
    - Commodities: CME/COMEX hours - Sunday 23:00 UTC → Friday 22:00 UTC (with daily break 21:00-22:00 UTC)
    - Stocks: Default to US market hours (NYSE/NASDAQ): Mon–Fri 13:30–20:00 UTC
      Note: This is a simplified schedule (no holidays). Override via env if needed.
    """
    if is_crypto(asset):
        return None

    now = now_utc or datetime.utcnow()
    wd = now.weekday()  # Monday=0 ... Sunday=6
    hr = now.hour
    minute = now.minute

    # Commodity schedule (CME/COMEX hours)
    # Gold/Silver: Sunday 23:00 UTC - Friday 22:00 UTC (with daily break 21:00-22:00 UTC)
    # Oil: Similar schedule
    if is_commodity(asset):
        # Check for holidays first
        holiday = is_commodity_holiday(now)
        if holiday:
            return holiday
        # Weekend closed
        if wd == 5:  # Saturday
            return "Commodities closed (Saturday)"
        if wd == 6 and hr < 23:  # Sunday before 23:00
            return "Commodities closed (Sunday until 23:00 UTC)"
        if wd == 4 and hr >= 22:  # Friday after 22:00
            return "Commodities closed (Friday after 22:00 UTC)"
        # Daily maintenance break (21:00-22:00 UTC Mon-Thu)
        if wd in (0, 1, 2, 3) and hr == 21:
            return "Commodities closed (daily maintenance 21:00-22:00 UTC)"
        return None

    # FX schedule
    if is_fx(asset):
        # Check for major holidays first (Christmas / New Year)
        try:
            from data.market_hours import is_fx_holiday
            fx_holiday = is_fx_holiday(now)
            if fx_holiday:
                return fx_holiday
        except Exception:
            pass
        # Friday after 22:00 UTC closed
        if wd == 4 and hr >= 22:
            return "FX closed Friday after 22:00 UTC"
        # Saturday fully closed
        if wd == 5:
            return "FX closed Saturday"
        # Sunday closed until 22:00 UTC
        if wd == 6 and hr < 22:
            return "FX closed Sunday until 22:00 UTC"
        return None

    # Stocks schedule (US default). Allow overrides via env:
    # STOCK_OPEN_UTC=13:30, STOCK_CLOSE_UTC=20:00 (HH:MM)
    if is_stock(asset):
        # Check for holidays first
        holiday = is_stock_holiday(now)
        if holiday:
            return holiday
        
        try:
            open_str = (os.getenv("STOCK_OPEN_UTC") or "13:30").strip()
            close_str = (os.getenv("STOCK_CLOSE_UTC") or "20:00").strip()
            oh, om = [int(x) for x in open_str.split(":")]
            ch, cm = [int(x) for x in close_str.split(":")]
        except Exception:
            oh, om = 13, 30
            ch, cm = 20, 0

        # Weekend closed
        if wd in (5, 6):
            return "Stocks closed (weekend)"

        # Weekday hours check
        after_open = (hr > oh) or (hr == oh and minute >= om)
        before_close = (hr < ch) or (hr == ch and minute <= cm)
        if after_open and before_close:
            return None
        return "Stocks closed (outside US market hours)"

    # Default: unknown type treated as open
    return None

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

    _binance_breaker = provider_breaker("binance")
    _bybit_breaker = provider_breaker("bybit")
    _cc_breaker = provider_breaker("cryptocompare")

    def _alert_provider_flip(from_provider: str, to_provider: str, reason: str) -> None:
        try:
            token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
            if not token:
                return
            from config import OWNER_IDS, ADMIN_IDS
            recipients = sorted({int(x) for x in ((OWNER_IDS or set()) | (ADMIN_IDS or set()))})
            if not recipients:
                return
            text = (
                "🚨 Provider Circuit Breaker Triggered\n"
                f"From: {from_provider}\n"
                f"To: {to_provider}\n"
                f"Reason: {reason}"
            )
            for rid in recipients:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": int(rid), "text": text},
                        timeout=6,
                    )
                except Exception:
                    continue
        except Exception:
            pass

    def _bybit_candles(symbol: str, tf: str) -> list[dict]:
        """Fetch candles from Bybit public API (free, often not geo-blocked)."""
        bybit_tf_map = {
            "5m": "5",
            "15m": "15",
            "1h": "60",
            "4h": "240",
            "1d": "1440",
        }
        bybit_interval = bybit_tf_map.get((tf or "").strip(), "60")
        url = "https://api.bybit.com/v5/market/klines"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": bybit_interval,
            "limit": 200,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            payload = resp.json() if resp.ok else {}
            if not resp.ok or str(payload.get("retCode") or "0") != "0":
                return []
            result = payload.get("result") or {}
            data = result.get("list") or []
            if not isinstance(data, list) or not data:
                return []
            out: list[dict] = []
            for row in data:
                try:
                    # Bybit returns [timestamp_ms, open, high, low, close, volume, ...]
                    ts_ms = int(row[0]) if row else 0
                    out.append(
                        {
                            "timestamp": ts_ms,
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]),
                        }
                    )
                except (IndexError, ValueError, TypeError):
                    continue
            logger.info(f"[data] crypto_fallback=bybit symbol={symbol} tf={tf} candles={len(out)}")
            return out
        except Exception:
            return []

    def _cryptocompare_candles(symbol_rest: str, tf: str) -> list[dict]:
        """Fetch candles from CryptoCompare public API (requires free key for higher limits)."""
        base_raw = (symbol_rest or "").upper().strip()
        if not base_raw:
            return []

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
        if not api_key:
            logger.warning(f"[data] cryptocompare_no_api_key symbol={sym} tf={tf}")
            return []
        if api_key:
            headers["authorization"] = f"Apikey {api_key}"

        def _fetch_for_quote(tsym: str) -> list[dict]:
            params_cc = {
                "fsym": base_raw,
                "tsym": tsym,
                "limit": 200,
                "aggregate": aggregate,
            }

            try:
                resp = requests.get(url_cc, params=params_cc, headers=headers, timeout=12)
            except Exception as e:
                logger.warning(f"[data] cryptocompare_request_failed symbol={base_raw} tsym={tsym} error={e}")
                return []
            
            payload = resp.json() if resp.ok else {}
            if not resp.ok:
                logger.warning(f"[data] cryptocompare_http_error symbol={base_raw} tsym={tsym} status={resp.status_code}")
                return []
            if str(payload.get("Response") or "").lower() != "success":
                logger.warning(f"[data] cryptocompare_api_error symbol={base_raw} tsym={tsym} response={payload.get('Response')}")
                return []

            data = (((payload.get("Data") or {}) or {}).get("Data") or [])
            if not isinstance(data, list) or not data:
                logger.warning(f"[data] cryptocompare_no_data symbol={base_raw} tsym={tsym}")
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
                logger.info(f"[data] crypto_fallback=cryptocompare symbol={base_raw}{tsym} tf={tf} candles={len(out)}")
                return out
        return []

    # First, try connector adapter if available (preferred, pluggable path)
    try:
        if _binance_breaker.allow():
            from data.connectors.binance_adapter import get_candles as connector_binance
            try:
                conn_out = connector_binance(sym, interval, limit=200)  # type: ignore
                if conn_out:
                    _binance_breaker.record_success()
                    logger.info(f"[data] crypto_connector=binance symbol={sym} tf={interval} candles={len(conn_out)}")
                    return conn_out
                opened = _binance_breaker.record_failure()
                if opened:
                    _alert_provider_flip("binance", "bybit", "connector_empty_response")
            except Exception:
                opened = _binance_breaker.record_failure()
                if opened:
                    _alert_provider_flip("binance", "bybit", "connector_exception")
        else:
            logger.warning("[data] circuit_open provider=binance symbol=%s tf=%s", sym, interval)
    except Exception:
        # Connector not available – continue with legacy providers
        pass

    # Allow explicit provider override (but still fall back if empty)
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
    
    # Nigeria fix: Binance blocked, prioritize CryptoCompare
    if provider == "cryptocompare":
        candles = _cryptocompare_candles(sym, interval) if _cc_breaker.allow() else []
        if candles:
            _cc_breaker.record_success()
        else:
            _cc_breaker.record_failure()
        if candles:
            return candles
    elif provider == "bybit":
        candles = _bybit_candles(sym, interval) if _bybit_breaker.allow() else []
        if candles:
            _bybit_breaker.record_success()
        else:
            _bybit_breaker.record_failure()
        if candles:
            return candles

    global _BINANCE_BLOCKED_REASON
    if _BINANCE_BLOCKED_REASON is not None:
        # Binance blocked: Try Bybit first, then CryptoCompare (NOT Yahoo/Twelve Data - they don't understand BTCUSDT format)
        logger.info(f"[data] binance_blocked={_BINANCE_BLOCKED_REASON} trying bybit/cryptocompare for {sym}")
        candles = _bybit_candles(sym, interval) if _bybit_breaker.allow() else []
        if candles:
            _bybit_breaker.record_success()
        else:
            _bybit_breaker.record_failure()
        if candles:
            return candles
        # Try CryptoCompare as fallback (it understands Binance notation)
        candles = _cryptocompare_candles(sym, interval) if _cc_breaker.allow() else []
        if candles:
            _cc_breaker.record_success()
        else:
            _cc_breaker.record_failure()
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
            logger.info(f"[data] crypto_primary=binance symbol={sym} tf={interval} candles={len(candles)}")
            _binance_breaker.record_success()
            return candles
        except Exception as e:
            opened = _binance_breaker.record_failure()
            if opened:
                _alert_provider_flip("binance", "bybit", "repeated_failures")
            print(f"[WARN] Binance candle fetch failed for {sym} {interval} (attempt {attempt}/{max_retries}): {e}")
            time.sleep(1)

    # Final fallback
    candles = _cryptocompare_candles(sym, interval)
    if candles:
        _cc_breaker.record_success()
        logger.info(f"[data] crypto_fallback=cryptocompare symbol={sym} tf={interval} candles={len(candles)}")
        return candles
    _cc_breaker.record_failure()
    logger.warning(f"[data] crypto_fetched=none symbol={sym} tf={interval} after_all_sources")
    return []

def get_fx_candles(asset, timeframe):
    """Fetch FX candles from a real candle provider.

    This intentionally avoids synthetic OHLC generation.
    Requires ALPHAVANTAGE_API_KEY to be set.
    """
    global _ALPHA_COOLDOWN_UNTIL
    now = time.monotonic()
    if now < _ALPHA_COOLDOWN_UNTIL:
        return []

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
        try:
            resp = requests.get(url, timeout=10)
            payload = resp.json() if resp.ok else {}
        except Exception as e:
            logger.error(f"[data] fx_fetch_error symbol={pair} tf={tf} error={e}")
            return []
        
        # AlphaVantage sends throttle notices in-body with 200 OK
        if any(k in payload for k in ("Note", "Information", "Error Message")):
            msg = payload.get("Note") or payload.get("Information") or payload.get("Error Message", "unknown")
            logger.warning(f"[data] fx_alphavantage_limit symbol={pair} tf={tf} msg={msg[:120]}")
            _ALPHA_COOLDOWN_UNTIL = time.monotonic() + max(20.0, _env_float("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", 20.0))
            return []
        key = f"Time Series FX ({interval})"
        series = payload.get(key) or {}
        if not series:
            logger.warning(f"[data] fx_no_data symbol={pair} tf={tf} keys={list(payload.keys())[:3]}")
            return []
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
        logger.info(f"[data] fx_primary=alphavantage symbol={pair} tf={tf} candles={len(candles)}")
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
                msg = payload.get("Note") or payload.get("Information") or payload.get("Error Message", "unknown")
                logger.warning(f"[data] fx_alphavantage_limit symbol={pair} tf={tf} msg={msg[:120]}")
                _ALPHA_COOLDOWN_UNTIL = time.monotonic() + max(20.0, _env_float("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", 20.0))
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
            logger.info(f"[data] fx_primary=alphavantage_agg60 symbol={pair} tf={tf} candles={len(out)}")
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
            msg = payload.get("Note") or payload.get("Information") or payload.get("Error Message", "unknown")
            logger.warning(f"[data] fx_alphavantage_limit symbol={pair} tf={tf} msg={msg[:120]}")
            _ALPHA_COOLDOWN_UNTIL = time.monotonic() + max(20.0, _env_float("ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS", 20.0))
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
        logger.info(f"[data] fx_primary=alphavantage_daily symbol={pair} tf={tf} candles={len(candles)}")
        return candles

    return []

def _env_bool(name: str, default: bool = False) -> bool:
    """Parse environment variable as boolean."""
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_tradingview_candles(asset: str, timeframe: str) -> list[dict]:
    """
    Fetch candles from TradingView using tradingview-ta library.
    
    This supplements Binance/CryptoCom/Bybit/AlphaVantage with additional data sources
    and pair coverage. Falls back gracefully if library not installed.
    
    Args:
        asset: Trading pair (e.g., 'BTCUSDT', 'EURUSD')
        timeframe: Timeframe (e.g., '1h', '4h', '1d')
    
    Returns:
        List of candle dicts with timestamp, open, high, low, close, volume
    """
    candles = []
    
    # Check if TradingView is enabled
    if not _env_bool("TRADINGVIEW_ENABLED", False):
        return candles
    
    try:
        from tradingview_ta import TA_Handler, Interval
        
        # Normalize timeframe to tradingview format
        tf_map = {
            '1m': Interval.INTERVAL_1_MINUTE,
            '5m': Interval.INTERVAL_5_MINUTES,
            '15m': Interval.INTERVAL_15_MINUTES,
            '1h': Interval.INTERVAL_1_HOUR,
            '4h': Interval.INTERVAL_4_HOURS,
            '1d': Interval.INTERVAL_1_DAY,
            '1w': Interval.INTERVAL_1_WEEK,
        }
        
        tv_tf = tf_map.get(timeframe.lower().strip())
        if tv_tf is None:
            return candles
        
        # Determine exchange and symbol format
        # Crypto: BINANCE for BTCUSDT/ETHUSDT (keep full pair)
        # Forex: FX_IDC for EURUSD/GBPUSD
        asset_upper = asset.upper().strip()

        if asset_upper.endswith(('USDT', 'BUSD', 'USDC', 'BTC', 'ETH')) or is_crypto(asset):
            exchange = 'BINANCE'
            symbol = asset_upper
        else:
            exchange = 'FX_IDC'
            symbol = asset_upper
        
        # Fetch analysis which includes indicator data
        try:
            handler = TA_Handler(
                symbol=symbol,
                screener='crypto' if exchange == 'BINANCE' else 'forex',
                exchange=exchange,
                interval=tv_tf,
            )
            
            analysis = handler.get_analysis()
			
            if analysis is None:
                return candles
            
            # TradingView doesn't directly provide candles, but we can use it
            # to validate the asset exists and get indicator-based analysis
            # For candle data, we fetch from primary source and validate with TradingView
            
            # If we got here, asset exists on TradingView - return indicator summary
            indicators = getattr(analysis, 'indicators', {})
            
            # Create a single synthetic candle with analysis metadata
            # This is used to enrich other data sources
            candle_meta = {
                'timestamp': datetime.utcnow().isoformat(),
                'open': 0.0,  # Placeholder - actual candles come from other sources
                'high': 0.0,
                'low': 0.0,
                'close': 0.0,
                'volume': 0.0,
                'tradingview_verified': True,
                'indicators_count': len([k for k in indicators.keys() if k != 'summary']),
            }
            logger.info(f"[data] tradingview_candles source=tradingview asset={asset_upper} tf={timeframe} verified=True")
            return [candle_meta]
        
        except Exception as e:
            # Asset might not exist on TradingView - that's OK
            return candles
        
    except ImportError:
        # tradingview-ta not installed - gracefully skip
        return candles
    except Exception as e:
        # Any other error - gracefully skip
        return candles


def discover_tradingview_symbols(exchange: str = "BINANCE") -> list[str]:
    """
    Discover available symbols from TradingView.
    
    This provides additional pair coverage beyond Binance/AlphaVantage.
    
    Args:
        exchange: "BINANCE" for crypto or "FX_IDC" for forex
    
    Returns:
        List of available symbol strings
    """
    symbols = []
    
    if not _env_bool("TRADINGVIEW_ENABLED", False):
        return symbols
    
    try:
        from tradingview_ta import Screener, Interval
        
        if exchange == 'BINANCE':
            # Get top crypto pairs from Binance on TradingView
            screener = Screener(screener='crypto', interval='1h')
            # TradingView screener returns top movers; we take a subset
            try:
                data = screener.get_crypto_screeners("BINANCE")
                # Extract symbols - vary by library version
                if isinstance(data, dict):
                    symbols = list(data.keys())[:50]  # Limit to top 50
                elif isinstance(data, list):
                    symbols = [d.get('symbol', '') for d in data if d.get('symbol')][:50]
            except Exception:
                pass
        
        elif exchange == 'FX_IDC':
            # Get forex pairs from FX_IDC on TradingView
            try:
                screener = Screener(screener='forex', interval='1d')
                data = screener.get_forex_screeners("FX_IDC")
                if isinstance(data, dict):
                    symbols = list(data.keys())[:30]  # Limit to top 30
                elif isinstance(data, list):
                    symbols = [d.get('symbol', '') for d in data if d.get('symbol')][:30]
            except Exception:
                pass
        
        return symbols
    
    except ImportError:
        return symbols
    except Exception:
        return symbols


async def async_get_candles(asset, timeframe):
    """Async variant of `get_candles` that prefers async connector callables.

    - If `USE_MULTI_PROVIDER_DATA` is false, runs the sync `get_candles` in a thread.
    - Otherwise uses `data.connector_registry.get_async_providers_for_asset` and
      `retry_async_httpx` to call providers without blocking the event loop.
    """
    try:
        asset_type = get_asset_type(asset)

        use_multi_provider = os.getenv("USE_MULTI_PROVIDER_DATA", "true").lower() == "true"
        if not use_multi_provider:
            return await asyncio.to_thread(get_candles, asset, timeframe)

        # Import registry locally to avoid import cycles at module import time
        from data.connector_registry import get_async_providers_for_asset

        # Build provider list in strict fallback order.
        provs = get_async_providers_for_asset(asset_type)

        symbol_for_providers = asset

        provider_timeout_s = 2.5
        for provider_name, fetch_fn in provs:
            try:
                # Strict per-provider timeout so slow upstreams fail fast and the chain can fallback.
                candles = await asyncio.wait_for(
                    fetch_fn(symbol_for_providers, timeframe, timeout=provider_timeout_s),
                    timeout=provider_timeout_s,
                )
                if candles and len(candles) >= 20:
                    mark_provider_result(provider_name, True)
                    logger.info(f"[data][async] provider={provider_name} symbol={asset} tf={timeframe} candles={len(candles)}")
                    return candles
                else:
                    mark_provider_result(provider_name, False)
            except asyncio.TimeoutError:
                mark_provider_result(provider_name, False)
                logger.warning(
                    f"[data][async] provider={provider_name} symbol={asset} timeout={provider_timeout_s}s"
                )
            except Exception as e:
                mark_provider_result(provider_name, False)
                logger.warning(f"[data][async] provider={provider_name} symbol={asset} failed: {e}")
                continue

        logger.warning("[WARN] All providers failed for %s, skipping...", asset)
        return []
    except Exception:
        logger.exception("async_get_candles failed for %s %s", asset, timeframe)
        return []
