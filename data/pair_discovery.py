import os
# --- Commodity asset discovery ---
def get_trending_commodity_tickers(top_n=10):
    """
    Return popular commodity tickers.
    Sources:
    1. Manual configuration via COMMODITY_TICKERS env var
    2. Default list (XAUUSD, XAGUSD, WTI, BRENT)
    """
    manual = (os.getenv("COMMODITY_TICKERS") or "").strip()
    if manual:
        tickers = [t.strip().upper() for t in manual.split(",") if t.strip()]
        return tickers[:top_n]
    # Default commodities
    default_commodities = ["XAUUSD", "XAGUSD", "WTI", "BRENT"]
    return default_commodities[:top_n]

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

logger = logging.getLogger(__name__)

# Global cache for auto-refreshed asset universe
_ASSET_UNIVERSE_CACHE = None
_ASSET_UNIVERSE_LAST_REFRESH = 0
_ASSET_UNIVERSE_REFRESH_INTERVAL = 3600  # seconds (1 hour)
_ASSET_UNIVERSE_LOCK = threading.Lock()

def _refresh_asset_universe():
    global _ASSET_UNIVERSE_CACHE, _ASSET_UNIVERSE_LAST_REFRESH
    with _ASSET_UNIVERSE_LOCK:
        _ASSET_UNIVERSE_CACHE = get_all_tradable_assets()
        _ASSET_UNIVERSE_LAST_REFRESH = time.time()

def get_latest_asset_universe(force_refresh=False):
    now = time.time()
    if force_refresh or _ASSET_UNIVERSE_CACHE is None or (now - _ASSET_UNIVERSE_LAST_REFRESH > _ASSET_UNIVERSE_REFRESH_INTERVAL):
        _refresh_asset_universe()
    return _ASSET_UNIVERSE_CACHE

def _asset_universe_auto_refresh_thread():
    while True:
        try:
            _refresh_asset_universe()
        except Exception as e:
            logger.warning("[pair_discovery] Asset universe auto-refresh failed: %s", e)
        time.sleep(_ASSET_UNIVERSE_REFRESH_INTERVAL)

import requests
from utils import proxy_manager

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

_BINANCE_DISABLED_REASON: str | None = None


# Default crypto symbols to pause until reliable intraday providers are configured.
# Includes DOGEIDR due to Polygon rate-limiting (429 errors)
_DEFAULT_CRYPTO_BLACKLIST = {"DOGEIDR"}

# Hardcoded fallback crypto pairs - used when all providers fail
# These are the top-tier liquid pairs that work even when APIs are blocked/rate-limited
_HARDCODED_CRYPTO_PAIRS: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
    "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "UNIUSDT", "XLMUSDT",
    "ETCUSDT", "XMRUSDT", "BCHUSDT", "ALGOUSDT", "XLMUSDT",
    "AAVEUSDT", "FILUSDT", "APEUSDT", "SANDUSDT", "MANAUSDT",
    "OPUSDT", "ARBUSDT", "NEARUSDT", "APTUSDT", "RNDRUSDT",
]

# Stablecoin pairs to exclude from trading (Bug Fix: "Stablecoin Trap")
# These pairs have minimal volatility and should not generate "trend" signals
STABLECOIN_PAIRS: set[str] = {
    "USDCUSDT", "USDCPERF", "DAIUSDT", "BUSDUSDT", "FDUSDUSDT",
    "USDTUSDC", "TUSDUSDT", "USDDUSDT", "FRAXUSDT", "MIMUSDT",
}


def _load_crypto_blacklist() -> set[str]:
    raw = (os.getenv("CRYPTO_BLACKLIST") or "").strip()
    extra = {x.strip().upper() for x in raw.split(",") if x.strip()}
    return _DEFAULT_CRYPTO_BLACKLIST | extra


_CRYPTO_BLACKLIST = _load_crypto_blacklist()


def _normalize_legacy_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    # Binance migrated Polygon from MATIC to POL.
    if s == "MATICUSDT":
        return "POLUSDT"
    return s


def _filter_blacklisted(pairs: list[str]) -> list[str]:
    if not pairs:
        return []
    EXCLUDE_ALWAYS = {"UNIUSDT", "APTUSDT"}
    out: list[str] = []
    for p in pairs:
        sym = _normalize_legacy_symbol(p)
        if sym in _CRYPTO_BLACKLIST or sym in EXCLUDE_ALWAYS:
            continue
        # Bug Fix: Filter stablecoin pairs to prevent "Stablecoin Trap" signals
        if sym in STABLECOIN_PAIRS:
            logger.info(f"[pair_discovery] Filtering stablecoin pair: {sym}")
            continue
        out.append(sym)
    return out


def _dedupe_limit(items: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    max_n = max(1, int(limit))
    for raw in items or []:
        sym = str(raw or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= max_n:
            break
    return out


def _is_true(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _merge_provider_results(provider_results: list[list[str]], limit: int) -> list[str]:
    """Merge provider lists in round-robin order for diversification."""
    merged: list[str] = []
    max_n = max(1, int(limit))
    idx = 0
    while len(merged) < max_n:
        progressed = False
        for arr in provider_results:
            if idx < len(arr):
                merged.append(arr[idx])
                progressed = True
                if len(merged) >= max_n:
                    break
        if not progressed:
            break
        idx += 1
    return _dedupe_limit(merged, max_n)


def _binance_top_crypto_pairs(top_n: int) -> list[str]:
    global _BINANCE_DISABLED_REASON
    if _BINANCE_DISABLED_REASON is not None:
        return []
    try:
        px = proxy_manager.ccxt_proxy_config_sync().get("proxies") or None
        resp = requests.get(BINANCE_API, timeout=5, proxies=px)
        data = resp.json()
        if isinstance(data, dict):
            code = data.get("code")
            msg = data.get("msg")
            msg_s = str(msg or "")
            if "restricted location" in msg_s.lower():
                _BINANCE_DISABLED_REASON = msg_s
                logger.warning("[pair_discovery] Binance pairs disabled: %s", msg_s)
                # Auto-switch crypto discovery/ingest to CryptoCompare to bypass geoblock
                if not os.getenv("CRYPTO_DATA_PROVIDER"):
                    os.environ["CRYPTO_DATA_PROVIDER"] = "cryptocompare"
                    os.environ.setdefault("CRYPTO_WS_PROVIDER", "cryptocompare")
                    logger.info("[pair_discovery] Switched crypto data provider to cryptocompare to bypass Binance geoblock")
                return []
            raise RuntimeError(f"Binance API error: code={code} msg={msg}")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Binance API response type: {type(data).__name__}")
        sorted_pairs = sorted(data, key=lambda x: float(x["quoteVolume"]), reverse=True)
        return _filter_blacklisted([x["symbol"] for x in sorted_pairs[: max(1, int(top_n))]])
    except Exception as e:
        logger.warning("[pair_discovery] Binance provider failed: %s", e)
        return []


def _cryptocompare_top_crypto_pairs(top_n: int) -> list[str]:
    """Best-effort fallback crypto universe via CryptoCompare.

    Returns Binance-style symbols like BTCUSDT, ETHUSDT.
    """

    try:
        limit = max(1, int(top_n))
    except Exception:
        limit = 20

    # CryptoCompare gives us top coins by total volume in a quote currency.
    # Use USD to maximize availability; we'll still map to *USDT symbols* for our engine.
    url = "https://min-api.cryptocompare.com/data/top/totalvolfull"
    params = {"limit": int(limit), "tsym": "USD"}

    headers = {}
    api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
    if api_key:
        headers["authorization"] = f"Apikey {api_key}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        payload = resp.json() if resp.ok else {}
        if not resp.ok:
            return []
        if str(payload.get("Response") or "").lower() != "success":
            return []
        data = payload.get("Data") or []
        if not isinstance(data, list):
            return []
        out: list[str] = []
        for row in data:
            try:
                coin = (row.get("CoinInfo") or {}).get("Name")
                coin = str(coin or "").upper().strip()
                if not coin:
                    continue
                # Map to our engine's crypto convention.
                out.append(f"{coin}USDT")
            except Exception:
                continue
        return _filter_blacklisted(out)
    except Exception:
        return []

# Discover trending crypto pairs from Binance
def get_trending_crypto_pairs(top_n=20):
    global _BINANCE_DISABLED_REASON
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "").strip().lower()
    EXCLUDE_ALWAYS = {"UNIUSDT", "APTUSDT"}
    
    def exclude_pairs(pairs):
        out = []
        for p in pairs:
            sym = _normalize_legacy_symbol(p)
            if sym in EXCLUDE_ALWAYS:
                continue
            out.append(sym)
        return out
    
    # Check for manual override first - CRYPTO_PAIRS env var takes absolute priority
    manual = (os.getenv("CRYPTO_PAIRS") or "").strip()
    if manual:
        manual_pairs = [x.strip().upper() for x in manual.split(",") if x.strip()]
        if manual_pairs:
            logger.info("[pair_discovery] Using manual CRYPTO_PAIRS: %s", manual_pairs[:5])
            return exclude_pairs(_filter_blacklisted(manual_pairs[:top_n]))
    
    # FIX: Default to CryptoCompare because Railway IP ranges are geo-blocked by Binance
    # Check if running on Railway - default to CryptoCompare to avoid geoblock issues
    is_railway = _is_true(os.getenv("RAILWAY_SERVICE_NAME") or "") or _is_true(os.getenv("RAILWAY_ENVIRONMENT") or "")
    
    # Explicit provider override remains supported.
    if provider == "cryptocompare":
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to hardcoded if CryptoCompare explicitly requested but fails
        logger.warning("[pair_discovery] CryptoCompare explicitly requested but failed, using hardcoded fallback")
        return exclude_pairs(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]))
    
    if provider == "binance":
        binance_only = _binance_top_crypto_pairs(top_n)
        if binance_only:
            return exclude_pairs(binance_only)
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to hardcoded if Binance requested but fails
        logger.warning("[pair_discovery] Binance explicitly requested but failed, using hardcoded fallback")
        return exclude_pairs(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]))
    
    if provider == "bybit":
        bybit_result = _bybit_top_crypto_pairs(top_n)
        if bybit_result:
            return exclude_pairs(bybit_result)
        # Fallback to CryptoCompare if Bybit requested but fails
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        logger.warning("[pair_discovery] Bybit explicitly requested but failed, using hardcoded fallback")
        return exclude_pairs(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]))

    # FIX: On Railway, use CryptoCompare by default to avoid Binance geoblock
    if is_railway:
        logger.info("[pair_discovery] Railway detected, using CryptoCompare by default to avoid Binance geoblock")
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to hardcoded
        logger.warning("[pair_discovery] CryptoCompare failed on Railway, using hardcoded fallback")
        return exclude_pairs(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]))

    # Default and "all": aggregate providers in parallel, fail-open.
    all_enabled = provider in {"all", "auto", ""} and _is_true(os.getenv("AUTO_DISCOVERY_ALL_PROVIDERS"), True)
    if all_enabled:
        provider_jobs = {
            "binance": lambda: _binance_top_crypto_pairs(top_n=max(1, int(top_n))),
            "cryptocompare": lambda: _filter_blacklisted(_cryptocompare_top_crypto_pairs(top_n=max(1, int(top_n)))),
        }
        results: dict[str, list[str]] = {}
        with ThreadPoolExecutor(max_workers=len(provider_jobs)) as ex:
            fut_map = {ex.submit(fn): name for name, fn in provider_jobs.items()}
            for fut in as_completed(fut_map):
                name = fut_map[fut]
                try:
                    results[name] = list(fut.result() or [])
                except Exception as e:
                    logger.warning("[pair_discovery] crypto provider %s failed: %s", name, e)
                    results[name] = []
        merged = _merge_provider_results(
            [results.get("binance", []), results.get("cryptocompare", [])],
            limit=max(1, int(top_n)),
        )
        if merged:
            return exclude_pairs(merged)

    # Final fail-open fallback: try Binance first, then CryptoCompare, then HARDCODED
    # Try CryptoCompare first (safer for Railway)
    fallback = _cryptocompare_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(_filter_blacklisted(fallback))
    
    # Then try Binance
    fallback = _binance_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(fallback)
    
    # CRITICAL FIX: Use hardcoded pairs when ALL providers fail (the "Total Scanned: 0" fix)
    logger.warning("[pair_discovery] All providers failed, using hardcoded fallback pairs")
    return exclude_pairs(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]))

def get_trending_fx_pairs():
    """Return configured FX pairs.

    FX pairs are optional and must be explicitly configured.

    Configure via FX_PAIRS (comma-separated), e.g. FX_PAIRS="EURUSD,GBPUSD,USDJPY".
    """
    raw = (os.getenv("FX_PAIRS") or "").strip()
    if not raw:
        # If a candle provider key is available, default to a reasonable set of majors.
        # Opt-out by setting FX_DEFAULT_ENABLED=0.
        enabled = (os.getenv("FX_DEFAULT_ENABLED") or "1").strip().lower() in {"1", "true", "yes", "y", "on"}
        if not enabled:
            return []
        if not (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip():
            return []
        return [
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USDCHF",
            "AUDUSD",
            "USDCAD",
            "NZDUSD",
            "EURJPY",
            "GBPJPY",
            "EURGBP",
        ]
    return [x.strip().upper() for x in raw.split(",") if x.strip()]

# Combine all pairs for strategy engine
def get_all_trending_pairs():
    try:
        top_n = int((os.getenv("CRYPTO_TRENDING_TOP_N") or os.getenv("CRYPTO_UNIVERSE_TOP_N") or "30").strip())
    except Exception:
        top_n = 30
    stock_top_n = max(1, int(os.getenv("STOCK_TRENDING_TOP_N", "20")))
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            "crypto": ex.submit(partial(get_trending_crypto_pairs, top_n=max(1, top_n))),
            "fx": ex.submit(get_trending_fx_pairs),
            "stocks": ex.submit(partial(get_trending_stock_tickers, top_n=stock_top_n)),
            "commodities": ex.submit(partial(get_trending_commodity_tickers, 10)),
        }
        out: dict[str, list[str]] = {"crypto": [], "fx": [], "stocks": [], "commodities": []}
        for k, fut in futures.items():
            try:
                out[k] = list(fut.result() or [])
            except Exception as e:
                logger.warning("[pair_discovery] %s discovery failed: %s", k, e)
                out[k] = []
    crypto = out["crypto"]
    fx = out["fx"]
    stocks = out["stocks"]
    commodities = out["commodities"]
    return crypto + fx + stocks + commodities


def get_trending_stock_tickers(top_n=20):
    """
    Return popular stock tickers.
    
    Sources (in order of preference):
    1. Manual configuration via STOCK_TICKERS env var
    2. S&P 500 most liquid stocks (hardcoded list)
    3. Polygon.io trending stocks API (if API key available)
    """
    # 1. Manual configuration
    manual = (os.getenv("STOCK_TICKERS") or "").strip()
    if manual:
        tickers = [t.strip().upper() for t in manual.split(",") if t.strip()]
        return tickers[:top_n]
    
    # 2. Hardcoded S&P 500 most liquid stocks
    sp500_liquid = [
        # Mega caps (FAANG+)
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
        # Tech
        "AMD", "INTC", "NFLX", "ADBE", "CRM", "ORCL", "CSCO",
        # Finance
        "JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA",
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "TMO", "MRK", "ABT",
        # Consumer
        "WMT", "HD", "DIS", "NKE", "MCD", "SBUX", "KO", "PEP",
        # Industrial
        "BA", "CAT", "GE", "MMM", "HON",
        # Energy
        "XOM", "CVX", "COP", "SLB",
        # Communication
        "T", "VZ", "CMCSA",
    ]
    
    def _polygon_provider() -> list[str]:
        polygon_key = os.getenv("POLYGON_API_KEY", "").strip()
        if not polygon_key:
            return []
        try:
            url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            params = {"apiKey": polygon_key}
            resp = requests.get(url, params=params, timeout=10)
            if not resp.ok:
                return []
            data = resp.json()
            tickers_data = data.get("tickers", [])
            if not tickers_data:
                return []
            sorted_tickers = sorted(
                tickers_data,
                key=lambda x: x.get("day", {}).get("v", 0),
                reverse=True
            )
            return [str(t.get("ticker") or "").upper().strip() for t in sorted_tickers[: max(1, int(top_n)) * 2]]
        except Exception as e:
            logger.warning("[pair_discovery] Polygon stocks fetch failed: %s", e)
            return []

    all_enabled = _is_true(os.getenv("AUTO_DISCOVERY_ALL_PROVIDERS"), True)
    if all_enabled:
        provider_results: list[list[str]] = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [
                ex.submit(_polygon_provider),
                ex.submit(lambda: list(sp500_liquid)),
            ]
            for fut in futures:
                try:
                    provider_results.append(list(fut.result() or []))
                except Exception as e:
                    logger.warning("[pair_discovery] stock provider failed: %s", e)
                    provider_results.append([])
        merged = _merge_provider_results(provider_results, limit=max(1, int(top_n)))
        if merged:
            return merged

    polygon_only = _polygon_provider()
    if polygon_only:
        return _dedupe_limit(polygon_only + sp500_liquid, max(1, int(top_n)))
    return sp500_liquid[:top_n]


def get_all_tradable_assets(crypto_limit=20, stock_limit=20):
    """
    Get all tradable assets (crypto + FX + stocks).
    
    Returns:
        dict with keys: crypto, fx, stocks, commodities
    """
    crypto = get_trending_crypto_pairs(crypto_limit)
    fx = get_trending_fx_pairs()
    stocks = get_trending_stock_tickers(stock_limit)
    commodities = get_trending_commodity_tickers(10)
    
    return {
        "crypto": crypto,
        "fx": fx,
        "stocks": stocks,
        "commodities": commodities,
    }

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)

if "pytest" not in sys.modules and str(os.getenv("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "0") or "0").strip().lower() not in {"1", "true", "yes", "y", "on"}:
    # Start auto-refresh thread at import time (after concrete discovery functions exist).
    _t = threading.Thread(target=_asset_universe_auto_refresh_thread, daemon=True)
    _t.start()
