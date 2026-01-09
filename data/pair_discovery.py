import os
import requests

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

_BINANCE_DISABLED_REASON: str | None = None


# Default crypto symbols to pause until reliable intraday providers are configured.
_DEFAULT_CRYPTO_BLACKLIST = set()


def _load_crypto_blacklist() -> set[str]:
    raw = (os.getenv("CRYPTO_BLACKLIST") or "").strip()
    extra = {x.strip().upper() for x in raw.split(",") if x.strip()}
    return _DEFAULT_CRYPTO_BLACKLIST | extra


_CRYPTO_BLACKLIST = _load_crypto_blacklist()


def _filter_blacklisted(pairs: list[str]) -> list[str]:
    if not pairs:
        return []
    return [p for p in pairs if p.upper() not in _CRYPTO_BLACKLIST]


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
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
    EXCLUDE_ALWAYS = {"UNIUSDT", "APTUSDT"}
    def exclude_pairs(pairs):
        return [p for p in pairs if p.upper() not in EXCLUDE_ALWAYS]
    if provider == "cryptocompare":
        return exclude_pairs(_filter_blacklisted(_cryptocompare_top_crypto_pairs(top_n)))
    if _BINANCE_DISABLED_REASON is not None:
        # Fallback universe when Binance is blocked.
        return exclude_pairs(_filter_blacklisted(_cryptocompare_top_crypto_pairs(top_n)))
    try:
        resp = requests.get(BINANCE_API, timeout=5)
        data = resp.json()

        # Binance normally returns a list[dict]. If we get a dict, it's usually an
        # error payload (e.g. rate limit) or an unexpected response shape.
        if isinstance(data, dict):
            code = data.get("code")
            msg = data.get("msg")
            msg_s = str(msg or "")
            # Railway regions can be blocked by Binance; disable further attempts
            # to avoid spamming logs.
            if "restricted location" in msg_s.lower():
                _BINANCE_DISABLED_REASON = msg_s
                print(f"[WARN] Binance pairs disabled: {msg_s}")
                return _cryptocompare_top_crypto_pairs(top_n)
            raise RuntimeError(f"Binance API error: code={code} msg={msg}")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Binance API response type: {type(data).__name__}")
        # Sort by quoteVolume (trending)
        sorted_pairs = sorted(data, key=lambda x: float(x['quoteVolume']), reverse=True)
        return _filter_blacklisted([x['symbol'] for x in sorted_pairs[:top_n]])
    except Exception as e:
        print(f"[WARN] Could not fetch Binance pairs: {e}")
        return _filter_blacklisted(_cryptocompare_top_crypto_pairs(top_n))

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
    crypto = get_trending_crypto_pairs(top_n=max(1, top_n))
    fx = get_trending_fx_pairs()
    stocks = get_trending_stock_tickers(top_n=max(1, int(os.getenv("STOCK_TRENDING_TOP_N", "20"))))
    return crypto + fx + stocks


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
    
    # 3. Polygon.io trending (if API key available)
    polygon_key = os.getenv("POLYGON_API_KEY", "").strip()
    if polygon_key:
        try:
            # Polygon snapshot endpoint for top gainers/losers/actives
            url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            params = {"apiKey": polygon_key}
            resp = requests.get(url, params=params, timeout=10)
            if resp.ok:
                data = resp.json()
                tickers_data = data.get("tickers", [])
                if tickers_data:
                    # Sort by volume
                    sorted_tickers = sorted(
                        tickers_data,
                        key=lambda x: x.get("day", {}).get("v", 0),
                        reverse=True
                    )
                    polygon_tickers = [t["ticker"] for t in sorted_tickers[:top_n * 2]]
                    # Merge with hardcoded list
                    combined = []
                    for ticker in polygon_tickers + sp500_liquid:
                        if ticker not in combined:
                            combined.append(ticker)
                    return combined[:top_n]
        except Exception as e:
            print(f"[WARN] Polygon stocks fetch failed: {e}")
    
    # Fallback to hardcoded list
    return sp500_liquid[:top_n]


def get_all_tradable_assets(crypto_limit=20, stock_limit=20):
    """
    Get all tradable assets (crypto + FX + stocks).
    
    Returns:
        dict with keys: crypto, fx, stocks
    """
    crypto = get_trending_crypto_pairs(crypto_limit)
    fx = get_trending_fx_pairs()
    stocks = get_trending_stock_tickers(stock_limit)
    
    return {
        "crypto": crypto,
        "fx": fx,
        "stocks": stocks,
    }

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)
