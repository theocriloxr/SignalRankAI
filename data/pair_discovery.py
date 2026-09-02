import os
# --- Commodity asset discovery ---
def get_trending_commodity_tickers(top_n=10):
    """Discover commodities from the configured broker, then explicit config."""
    try:
        broker_symbols = _metaapi_symbols()
    except NameError:  # function is defined before the helper during module import
        broker_symbols = []
    markers = ("XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER", "WTI", "BRENT", "OIL", "NGAS", "COPPER")
    discovered = [symbol for symbol in broker_symbols if any(marker in str(symbol).upper() for marker in markers)]
    if discovered:
        return _record_provider_symbols(_dedupe_limit(discovered, max(1, int(top_n))), "metaapi")
    manual = (os.getenv("COMMODITY_TICKERS") or "").strip()
    if manual:
        return _record_provider_symbols(_dedupe_limit([t.strip().upper() for t in manual.split(",") if t.strip()], max(1, int(top_n))), "manual_config")
    if _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False):
        return _record_provider_symbols(["XAUUSD", "XAGUSD", "WTI", "BRENT"][:top_n], "static_fallback")
    return []

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
_ASSET_UNIVERSE_THREAD: threading.Thread | None = None
_ASSET_UNIVERSE_THREAD_LOCK = threading.Lock()
_ASSET_DISCOVERY_PROVENANCE: dict[str, set[str]] = {}
_ASSET_DISCOVERY_PROVENANCE_LOCK = threading.Lock()
_METAAPI_SYMBOL_CACHE: list[str] = []
_METAAPI_SYMBOL_CACHE_AT = 0.0
_METAAPI_SYMBOL_CACHE_LOCK = threading.Lock()


def _record_provider_symbols(symbols: list[str], provider: str) -> list[str]:
    """Record where each discovered symbol came from without changing ordering."""
    cleaned = [str(x or "").upper().strip() for x in (symbols or []) if str(x or "").strip()]
    source = str(provider or "unknown").strip().lower() or "unknown"
    with _ASSET_DISCOVERY_PROVENANCE_LOCK:
        for symbol in cleaned:
            _ASSET_DISCOVERY_PROVENANCE.setdefault(symbol, set()).add(source)
    return cleaned


def asset_discovery_provenance(asset: str) -> str:
    """Return provider-backed provenance for an admitted asset.

    Static or manual-only symbols are intentionally identified so live execution
    can fail closed unless the symbol has also been discovered from a provider.
    """
    symbol = str(asset or "").upper().strip()
    if not symbol:
        return ""
    with _ASSET_DISCOVERY_PROVENANCE_LOCK:
        providers = set(_ASSET_DISCOVERY_PROVENANCE.get(symbol) or set())
    trusted = sorted(p for p in providers if p not in {"manual_config", "static_fallback", "unknown"})
    return ",".join(trusted)


def asset_discovery_sources(asset: str) -> tuple[str, ...]:
    symbol = str(asset or "").upper().strip()
    with _ASSET_DISCOVERY_PROVENANCE_LOCK:
        return tuple(sorted(_ASSET_DISCOVERY_PROVENANCE.get(symbol) or set()))

def _refresh_asset_universe():
    global _ASSET_UNIVERSE_CACHE, _ASSET_UNIVERSE_LAST_REFRESH
    with _ASSET_UNIVERSE_LOCK:
        # Provenance belongs to the current discovery snapshot. Keeping sources
        # from an earlier successful refresh can falsely certify an asset after
        # its provider is no longer reachable.
        with _ASSET_DISCOVERY_PROVENANCE_LOCK:
            _ASSET_DISCOVERY_PROVENANCE.clear()
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


def start_asset_universe_refresh_thread() -> bool:
    """Start the optional discovery refresh thread exactly once.

    Discovery is lazy by default. Importing this module must not perform network
    I/O or create duplicate provider traffic in every Railway process.
    """
    global _ASSET_UNIVERSE_THREAD
    with _ASSET_UNIVERSE_THREAD_LOCK:
        if _ASSET_UNIVERSE_THREAD is not None and _ASSET_UNIVERSE_THREAD.is_alive():
            return False
        thread = threading.Thread(
            target=_asset_universe_auto_refresh_thread,
            name="asset-universe-refresh",
            daemon=True,
        )
        thread.start()
        _ASSET_UNIVERSE_THREAD = thread
        return True

import requests
from utils import proxy_manager
from core.env import runtime_environment_name

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
BYBIT_API = 'https://api.bybit.com/v5/market/tickers'
BYBIT_CATEGORY = 'linear'
OKX_TICKERS_API = 'https://www.okx.com/api/v5/market/tickers'
OKX_INSTRUMENTS_API = 'https://www.okx.com/api/v5/public/instruments'
BYBIT_INSTRUMENTS_API = 'https://api.bybit.com/v5/market/instruments-info'
COINBASE_PRODUCTS_API = 'https://api.exchange.coinbase.com/products'
COINBASE_PRODUCT_STATS_API = 'https://api.exchange.coinbase.com/products/{product_id}/stats'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

_BINANCE_DISABLED_REASON: str | None = None
_BYBIT_DISABLED_REASON: str | None = None


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
    "USDTUSDC", "USDTUSDT", "TUSDUSDT", "USDEUSDT", "USDDUSDT",
    "FRAXUSDT", "MIMUSDT",
}


def _is_non_trading_quote_asset(symbol: str) -> bool:
    """Reject quote/stablecoin inventory mapped into synthetic USDT pairs."""
    value = str(symbol or "").upper().strip()
    base = value[:-4] if value.endswith("USDT") else value
    return base in {"U", "UB"} or base.startswith("USD") or base in {
        "USAT", "USBD", "USDCV", "DAI", "BUSD", "FDUSD", "TUSD",
        "USDE", "USDD", "FRAX", "MIM",
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
        if sym in STABLECOIN_PAIRS or _is_non_trading_quote_asset(sym):
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
        return _record_provider_symbols(_filter_blacklisted([x["symbol"] for x in sorted_pairs[: max(1, int(top_n))]]), "binance")
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
        return _record_provider_symbols(_filter_blacklisted(out), "cryptocompare")
    except Exception:
        return []


def _bybit_top_crypto_pairs(top_n: int) -> list[str]:
    """Discover active liquid Bybit spot USDT instruments.

    Instrument status and market liquidity are fetched independently and
    intersected, preventing delisted/prelaunch symbols from entering the engine.
    """
    global _BYBIT_DISABLED_REASON
    if _BYBIT_DISABLED_REASON is not None:
        return []
    try:
        limit = max(1, int(top_n))
        instrument_resp = requests.get(
            BYBIT_INSTRUMENTS_API,
            params={"category": "spot", "status": "Trading"},
            timeout=8,
        )
        ticker_resp = requests.get(BYBIT_API, params={"category": "spot"}, timeout=8)
        instrument_payload = instrument_resp.json() if instrument_resp.ok else {}
        ticker_payload = ticker_resp.json() if ticker_resp.ok else {}
        for payload in (instrument_payload, ticker_payload):
            if int(payload.get("retCode", -1)) != 0:
                message = str(payload.get("retMsg") or "")
                if "restricted" in message.lower() or "location" in message.lower():
                    _BYBIT_DISABLED_REASON = message
                return []
        active = {
            str(row.get("symbol") or "").upper().strip()
            for row in (instrument_payload.get("result", {}).get("list") or [])
            if str(row.get("status") or "Trading").lower() == "trading"
            and str(row.get("quoteCoin") or "").upper() == "USDT"
        }
        minimum_quote_volume = float(os.getenv("ASSET_DISCOVERY_MIN_QUOTE_VOLUME_USD", "1000000") or 1000000)
        ranked = sorted(
            ticker_payload.get("result", {}).get("list") or [],
            key=lambda row: float(row.get("turnover24h") or row.get("volume24h") or 0.0),
            reverse=True,
        )
        out = []
        for row in ranked:
            symbol = str(row.get("symbol") or "").upper().strip()
            turnover = float(row.get("turnover24h") or 0.0)
            if symbol not in active or not symbol.endswith("USDT") or turnover < minimum_quote_volume:
                continue
            out.append(symbol)
            if len(out) >= limit:
                break
        return _record_provider_symbols(_filter_blacklisted(out), "bybit")
    except Exception as exc:
        logger.debug("[pair_discovery] Bybit provider failed: %s", exc)
        return []


def _okx_top_crypto_pairs(top_n: int) -> list[str]:
    """Discover live, liquid OKX USDT spot instruments."""
    try:
        instrument_resp = requests.get(OKX_INSTRUMENTS_API, params={"instType": "SPOT"}, timeout=8)
        ticker_resp = requests.get(OKX_TICKERS_API, params={"instType": "SPOT"}, timeout=8)
        instrument_payload = instrument_resp.json() if instrument_resp.ok else {}
        ticker_payload = ticker_resp.json() if ticker_resp.ok else {}
        if str(instrument_payload.get("code") or "") != "0" or str(ticker_payload.get("code") or "") != "0":
            return []
        active = {
            str(row.get("instId") or "").upper().strip()
            for row in (instrument_payload.get("data") or [])
            if str(row.get("state") or "live").lower() == "live"
            and str(row.get("quoteCcy") or "").upper() == "USDT"
        }
        minimum_quote_volume = float(os.getenv("ASSET_DISCOVERY_MIN_QUOTE_VOLUME_USD", "1000000") or 1000000)
        ranked = sorted(
            ticker_payload.get("data") or [],
            key=lambda row: float(row.get("volCcy24h") or 0.0),
            reverse=True,
        )
        pairs: list[str] = []
        for row in ranked:
            instrument = str(row.get("instId") or "").upper().strip()
            quote_volume = float(row.get("volCcy24h") or 0.0)
            if instrument not in active or not instrument.endswith("-USDT") or quote_volume < minimum_quote_volume:
                continue
            pairs.append(instrument.replace("-", ""))
            if len(pairs) >= max(1, int(top_n)):
                break
        return _record_provider_symbols(_filter_blacklisted(pairs), "okx")
    except Exception as exc:
        logger.debug("[pair_discovery] OKX provider failed: %s", exc)
        return []


def _coinbase_top_crypto_pairs(top_n: int) -> list[str]:
    """Discover liquid Coinbase Exchange spot products via public endpoints.

    The Advanced Trade brokerage catalogue requires authentication in some
    deployments. The Exchange ``/products`` and per-product ``/stats`` routes
    are public and therefore suitable for provider discovery.
    """
    try:
        limit = max(1, int(top_n))
        response = requests.get(
            COINBASE_PRODUCTS_API,
            headers={"Accept": "application/json", "User-Agent": "SignalRankAI/asset-discovery"},
            timeout=10,
        )
        products = response.json() if response.ok else []
        if not isinstance(products, list):
            return []
        candidates: list[tuple[str, str]] = []
        for row in products:
            if not isinstance(row, dict):
                continue
            product_id = str(row.get("id") or row.get("product_id") or "").upper().strip()
            status = str(row.get("status") or "online").lower().strip()
            quote = str(row.get("quote_currency") or "").upper().strip()
            base = str(row.get("base_currency") or "").upper().strip()
            if not product_id or status not in {"online", "trading"}:
                continue
            if quote not in {"USD", "USDT"} or not base:
                continue
            if bool(row.get("cancel_only")) or bool(row.get("limit_only")) or bool(row.get("trading_disabled")):
                continue
            candidates.append((product_id, base))
        # Bound stats traffic while retaining enough candidates to rank by
        # notional volume. Product order from the catalogue is not a liquidity
        # ranking.
        stats_limit = min(len(candidates), max(25, limit * 4), 100)
        candidates = candidates[:stats_limit]
        minimum_quote_volume = float(os.getenv("ASSET_DISCOVERY_MIN_QUOTE_VOLUME_USD", "1000000") or 1000000)

        def _stats(item: tuple[str, str]) -> tuple[str, float]:
            product_id, base = item
            try:
                resp = requests.get(
                    COINBASE_PRODUCT_STATS_API.format(product_id=product_id),
                    headers={"Accept": "application/json", "User-Agent": "SignalRankAI/asset-discovery"},
                    timeout=8,
                )
                payload = resp.json() if resp.ok else {}
                volume = float(payload.get("volume") or 0.0)
                last = float(payload.get("last") or payload.get("open") or 0.0)
                return base, max(0.0, volume * last)
            except Exception:
                return base, 0.0

        ranked: list[tuple[str, float]] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(candidates)))) as pool:
            futures = [pool.submit(_stats, item) for item in candidates]
            for future in as_completed(futures):
                ranked.append(future.result())
        ranked.sort(key=lambda item: item[1], reverse=True)
        out = [f"{base}USDT" for base, quote_volume in ranked if quote_volume >= minimum_quote_volume]
        return _record_provider_symbols(_filter_blacklisted(_dedupe_limit(out, limit)), "coinbase")
    except Exception as exc:
        logger.debug("[pair_discovery] Coinbase provider failed: %s", exc)
        return []


def _metaapi_symbols() -> list[str]:
    """Discover the exact instrument universe available on the configured MT account."""
    global _METAAPI_SYMBOL_CACHE, _METAAPI_SYMBOL_CACHE_AT
    token = str(os.getenv("META_API_TOKEN") or "").strip()
    account_id = str(os.getenv("META_API_ACCOUNT_ID") or "").strip()
    if not token or not account_id:
        return []
    region = str(os.getenv("META_API_REGION") or "new-york").strip().lower()
    host = f"https://mt-client-api-v1.{region}.agiliumtrade.ai"
    ttl = max(30.0, float(os.getenv("METAAPI_SYMBOL_CACHE_SECONDS", "300") or 300))
    with _METAAPI_SYMBOL_CACHE_LOCK:
        if _METAAPI_SYMBOL_CACHE and time.time() - _METAAPI_SYMBOL_CACHE_AT < ttl:
            return _record_provider_symbols(list(_METAAPI_SYMBOL_CACHE), "metaapi")
        try:
            response = requests.get(
                f"{host}/users/current/accounts/{account_id}/symbols",
                headers={"auth-token": token, "Accept": "application/json"},
                timeout=12,
            )
            payload = response.json() if response.ok else []
            if not isinstance(payload, list):
                return []
            _METAAPI_SYMBOL_CACHE = _dedupe_limit(
                [str(item or "").upper().strip() for item in payload],
                5000,
            )
            _METAAPI_SYMBOL_CACHE_AT = time.time()
            return _record_provider_symbols(list(_METAAPI_SYMBOL_CACHE), "metaapi")
        except Exception as exc:
            logger.debug("[pair_discovery] MetaApi symbol discovery failed: %s", exc)
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
    
    # Manual symbols supplement provider discovery by default. They become an
    # absolute universe only when explicitly requested; this prevents a stale
    # CRYPTO_PAIRS variable from silently disabling online asset discovery.
    manual = (os.getenv("CRYPTO_PAIRS") or "").strip()
    manual_pairs = [x.strip().upper() for x in manual.split(",") if x.strip()] if manual else []
    manual_symbols = exclude_pairs(
        _record_provider_symbols(_filter_blacklisted(manual_pairs), "manual_config")
    ) if manual_pairs else []
    discovery_mode = str(os.getenv("ASSET_DISCOVERY_MODE") or "auto").strip().lower()
    if manual_symbols and discovery_mode in {"manual", "fixed", "allowlist"}:
        logger.warning("[pair_discovery] explicit manual-only crypto universe enabled")
        return manual_symbols[: max(1, int(top_n))]
    
    # FIX: Default to CryptoCompare because Railway IP ranges are geo-blocked by Binance
    # Check if running on Railway - default to CryptoCompare to avoid geoblock issues
    is_railway = bool(str(os.getenv("RAILWAY_SERVICE_NAME") or "").strip()) or bool(
        str(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") or "").strip()
    )
    static_allowed = _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False)
    
    # Explicit provider override remains supported.
    if provider == "cryptocompare":
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to hardcoded if CryptoCompare explicitly requested but fails
        if static_allowed:
            logger.warning("[pair_discovery] CryptoCompare failed; using explicitly enabled static fallback")
            return exclude_pairs(_record_provider_symbols(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]), "static_fallback"))
        return []
    
    if provider == "binance":
        binance_only = _binance_top_crypto_pairs(top_n)
        if binance_only:
            return exclude_pairs(binance_only)
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to hardcoded if Binance requested but fails
        if static_allowed:
            logger.warning("[pair_discovery] Binance failed; using explicitly enabled static fallback")
            return exclude_pairs(_record_provider_symbols(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]), "static_fallback"))
        return []
    
# On Railway use the same public source that currently succeeds for candles.
    if is_railway:
        logger.info("[pair_discovery] Railway detected, trying OKX discovery first")
        result = _okx_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        result = _bybit_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        result = _coinbase_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Fallback to CryptoCompare if exchange discovery is unavailable
        logger.warning("[pair_discovery] Bybit failed on Railway, trying CryptoCompare")
        result = _cryptocompare_top_crypto_pairs(top_n)
        if result:
            return exclude_pairs(_filter_blacklisted(result))
        # Final fallback to hardcoded
        if static_allowed:
            logger.warning("[pair_discovery] All providers failed on Railway; static fallback explicitly enabled")
            return exclude_pairs(_record_provider_symbols(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]), "static_fallback"))
        logger.error("[pair_discovery] provider-backed crypto discovery unavailable; failing closed")
        return []

    # Default and "all": aggregate online providers in parallel; fail closed unless static fallback is explicitly enabled.
    all_enabled = provider in {"all", "auto", ""} and _is_true(os.getenv("AUTO_DISCOVERY_ALL_PROVIDERS"), True)
    if all_enabled:
        provider_jobs = {
            "okx": lambda: _okx_top_crypto_pairs(top_n=max(1, int(top_n))),
            "bybit": lambda: _bybit_top_crypto_pairs(top_n=max(1, int(top_n))),
            "coinbase": lambda: _coinbase_top_crypto_pairs(top_n=max(1, int(top_n))),
            "cryptocompare": lambda: _filter_blacklisted(_cryptocompare_top_crypto_pairs(top_n=max(1, int(top_n)))),
            "binance": lambda: _binance_top_crypto_pairs(top_n=max(1, int(top_n))),
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
            [results.get("okx", []), results.get("bybit", []), results.get("coinbase", []), results.get("cryptocompare", []), results.get("binance", []), manual_symbols],
            limit=max(1, int(top_n)),
        )
        if merged:
            return exclude_pairs(merged)

    # Sequential provider fallback; hardcoded assets remain disabled unless explicitly enabled.
    fallback = _okx_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(_filter_blacklisted(fallback))

    fallback = _bybit_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(_filter_blacklisted(fallback))

    fallback = _coinbase_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(_filter_blacklisted(fallback))

    fallback = _cryptocompare_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(_filter_blacklisted(fallback))
    
    # Then try Binance
    fallback = _binance_top_crypto_pairs(top_n)
    if fallback:
        return exclude_pairs(fallback)
    
    # CRITICAL FIX: Use hardcoded pairs when ALL providers fail (the "Total Scanned: 0" fix)
    if static_allowed:
        logger.warning("[pair_discovery] all providers failed; static fallback explicitly enabled")
        return exclude_pairs(_record_provider_symbols(_filter_blacklisted(_HARDCODED_CRYPTO_PAIRS[:top_n]), "static_fallback"))
    if runtime_environment_name("development") == "production":
        logger.error("[pair_discovery] production discovery failed closed; no hardcoded assets admitted")
    return []

def get_trending_fx_pairs():
    """Discover broker-supported FX pairs, with explicit configuration as fallback."""
    broker_symbols = _metaapi_symbols()
    fx = []
    for raw_symbol in broker_symbols:
        symbol = str(raw_symbol or "").upper().replace(".", "").replace("_", "")
        if len(symbol) >= 6 and symbol[:6].isalpha() and symbol[:3] in {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF"} and symbol[3:6] in {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF"}:
            fx.append(raw_symbol)
    if fx:
        return _record_provider_symbols(
            _dedupe_limit(fx, max(1, int(os.getenv("FX_UNIVERSE_TOP_N", "40") or 40))),
            "metaapi",
        )
    raw = (os.getenv("FX_PAIRS") or "").strip()
    if raw:
        return _record_provider_symbols(_dedupe_limit([x.strip().upper() for x in raw.split(",") if x.strip()], 100), "manual_config")
    if _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False):
        return _record_provider_symbols(["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP"], "static_fallback")
    return []

# Combine all pairs for strategy engine
def get_all_trending_pairs():
    try:
        top_n = int((os.getenv("CRYPTO_TRENDING_TOP_N") or os.getenv("CRYPTO_UNIVERSE_TOP_N") or "30").strip())
    except Exception:
        top_n = 30
    stock_top_n = max(1, int(os.getenv("STOCK_TRENDING_TOP_N", "20")))
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            "crypto": ex.submit(partial(get_trending_crypto_pairs, top_n=max(1, top_n))),
            "fx": ex.submit(get_trending_fx_pairs),
            "stocks": ex.submit(partial(get_trending_stock_tickers, top_n=stock_top_n)),
            "indices": ex.submit(partial(get_trending_index_tickers, top_n=max(1, int(os.getenv("INDEX_TRENDING_TOP_N", "20"))))),
            "commodities": ex.submit(partial(get_trending_commodity_tickers, 10)),
        }
        out: dict[str, list[str]] = {"crypto": [], "fx": [], "stocks": [], "indices": [], "commodities": []}
        for k, fut in futures.items():
            try:
                out[k] = list(fut.result() or [])
            except Exception as e:
                logger.warning("[pair_discovery] %s discovery failed: %s", k, e)
                out[k] = []
    crypto = out["crypto"]
    fx = out["fx"]
    stocks = out["stocks"]
    indices = out["indices"]
    commodities = out["commodities"]
    return crypto + fx + stocks + indices + commodities


def get_trending_stock_tickers(top_n=20):
    """Discover liquid equities from configured providers and the broker universe."""
    manual = (os.getenv("STOCK_TICKERS") or "").strip()
    manual_symbols = _record_provider_symbols(
        _dedupe_limit([t.strip().upper() for t in manual.split(",") if t.strip()], max(1, int(top_n))),
        "manual_config",
    ) if manual else []
    if manual_symbols and str(os.getenv("ASSET_DISCOVERY_MODE") or "auto").strip().lower() in {"manual", "fixed", "allowlist"}:
        return manual_symbols

    broker_symbols = _metaapi_symbols()
    # Broker equity symbols often include suffixes (.US, .NAS, _US). Preserve the
    # native symbol and let services.asset_mapper normalize provider-specific names.
    broker_equities = []
    fx_ccy = {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF"}
    for symbol in broker_symbols:
        compact = str(symbol or "").upper().replace(".", "").replace("_", "")
        if not compact or any(x in compact for x in ("US500","NAS100","US30","XAU","XAG","WTI","BRENT")):
            continue
        if len(compact) == 6 and compact[:3] in fx_ccy and compact[3:] in fx_ccy:
            continue
        if compact.endswith(("USD","USDT")) and len(compact) > 6:
            continue
        if 1 <= len(str(symbol)) <= 16 and any(ch.isalpha() for ch in str(symbol)):
            broker_equities.append(str(symbol).upper().strip())

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
            tickers_data = (resp.json() or {}).get("tickers", [])
            sorted_tickers = sorted(tickers_data, key=lambda x: x.get("day", {}).get("v", 0), reverse=True)
            minimum_volume = float(os.getenv("STOCK_DISCOVERY_MIN_DAILY_VOLUME", "1000000") or 1000000)
            return _record_provider_symbols([
                str(t.get("ticker") or "").upper().strip()
                for t in sorted_tickers
                if float((t.get("day") or {}).get("v") or 0.0) >= minimum_volume
            ], "polygon")
        except Exception as exc:
            logger.warning("[pair_discovery] Polygon stocks fetch failed: %s", exc)
            return []

    provider_results = [
        _polygon_provider(),
        _record_provider_symbols(broker_equities, "metaapi"),
        manual_symbols,
    ]
    merged = _merge_provider_results(provider_results, limit=max(1, int(top_n)))
    if merged:
        return merged
    if _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False):
        return _record_provider_symbols(["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "XOM"][:top_n], "static_fallback")
    return []


def get_trending_index_tickers(top_n=20):
    """Discover broker index/CFD symbols, preserving broker-native names."""
    broker_symbols = _metaapi_symbols()
    markers = ("US500", "SPX", "NAS", "USTEC", "US30", "DJ", "GER", "DE40", "UK100", "FTSE", "JP225", "NIKKEI", "FRA40", "EU50", "AUS200", "HK50")
    discovered = [symbol for symbol in broker_symbols if any(marker in str(symbol).upper() for marker in markers)]
    if discovered:
        return _record_provider_symbols(
            _dedupe_limit(discovered, max(1, int(top_n))),
            "metaapi",
        )
    manual = (os.getenv("INDEX_TICKERS") or "").strip()
    if manual:
        return _record_provider_symbols(_dedupe_limit([t.strip().upper() for t in manual.split(",") if t.strip()], max(1, int(top_n))), "manual_config")
    if _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False):
        return _record_provider_symbols(["US500", "NAS100", "US30", "GER40", "UK100", "JP225", "FRA40", "EU50", "AUS200", "HK50"][:top_n], "static_fallback")
    return []


def get_all_tradable_assets(crypto_limit=20, stock_limit=20):
    """
    Get all tradable assets (crypto + FX + stocks + indices + commodities).
    
    Returns:
        dict with keys: crypto, fx, stocks, indices, commodities
    """
    jobs = {
        "crypto": partial(get_trending_crypto_pairs, top_n=max(1, int(crypto_limit))),
        "fx": get_trending_fx_pairs,
        "stocks": partial(get_trending_stock_tickers, top_n=max(1, int(stock_limit))),
        "indices": partial(
            get_trending_index_tickers,
            top_n=max(1, int(os.getenv("INDEX_TRENDING_TOP_N", "20"))),
        ),
        "commodities": partial(get_trending_commodity_tickers, 10),
    }
    universe: dict[str, list[str]] = {name: [] for name in jobs}
    # Provider discovery is independent by class. Running it concurrently keeps
    # a slow broker catalogue from serially delaying the engine startup for each
    # FX/equity/index/commodity query.
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        future_map = {executor.submit(job): name for name, job in jobs.items()}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                universe[name] = list(future.result() or [])
            except Exception as exc:
                logger.warning("[pair_discovery] %s universe discovery failed: %s", name, exc)
    return universe


def get_asset_discovery_snapshot(force_refresh: bool = False) -> dict:
    """Return observable dynamic-discovery state for owner/admin diagnostics."""
    try:
        universe = get_latest_asset_universe(force_refresh=force_refresh)
    except Exception as exc:
        universe = {}
        error = str(exc)[:200]
    else:
        error = ""

    if not isinstance(universe, dict):
        universe = {}
    normalized = {
        "crypto": list(universe.get("crypto") or []),
        "fx": list(universe.get("fx") or []),
        "stocks": list(universe.get("stocks") or []),
        "indices": list(universe.get("indices") or []),
        "commodities": list(universe.get("commodities") or []),
    }
    all_symbols: list[str] = []
    for values in normalized.values():
        all_symbols.extend(str(x or "").upper().strip() for x in values if str(x or "").strip())
    unique_symbols = list(dict.fromkeys(all_symbols))
    trusted_symbols = [symbol for symbol in unique_symbols if asset_discovery_provenance(symbol)]
    untrusted_symbols = [symbol for symbol in unique_symbols if not asset_discovery_provenance(symbol)]
    trusted_ratio = (len(trusted_symbols) / len(unique_symbols)) if unique_symbols else 0.0
    return {
        "last_refresh_age_seconds": max(0.0, time.time() - float(_ASSET_UNIVERSE_LAST_REFRESH or 0)),
        "refresh_interval_seconds": int(_ASSET_UNIVERSE_REFRESH_INTERVAL),
        "counts": {key: len(value) for key, value in normalized.items()},
        "total": len(unique_symbols),
        "trusted_provider_total": len(trusted_symbols),
        "untrusted_total": len(untrusted_symbols),
        "trusted_provider_ratio": round(trusted_ratio, 4),
        "untrusted_samples": untrusted_symbols[:25],
        "samples": {key: value[:10] for key, value in normalized.items()},
        "provenance_samples": {symbol: list(asset_discovery_sources(symbol)) for symbol in unique_symbols[:25]},
        "providers": {
            "binance_disabled": bool(_BINANCE_DISABLED_REASON),
            "binance_reason": _BINANCE_DISABLED_REASON,
            "bybit_disabled": bool(_BYBIT_DISABLED_REASON),
            "bybit_reason": _BYBIT_DISABLED_REASON,
            "crypto_provider": (os.getenv("CRYPTO_DATA_PROVIDER") or "auto").strip() or "auto",
            "auto_all_providers": _is_true(os.getenv("AUTO_DISCOVERY_ALL_PROVIDERS"), True),
            "static_fallback_enabled": _is_true(os.getenv("ALLOW_STATIC_ASSET_FALLBACK"), False),
            "provider_backed": bool(unique_symbols) and len(trusted_symbols) == len(unique_symbols),
            "trusted_provider_ratio": round(trusted_ratio, 4),
        },
        "error": error,
    }

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)

if (
    "pytest" not in sys.modules
    and str(os.getenv("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "0") or "0").strip().lower()
    not in {"1", "true", "yes", "y", "on"}
    and str(os.getenv("ASSET_UNIVERSE_BACKGROUND_REFRESH_ENABLED", "0") or "0").strip().lower()
    in {"1", "true", "yes", "y", "on"}
):
    start_asset_universe_refresh_thread()
