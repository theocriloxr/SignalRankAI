import os
import requests

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

_BINANCE_DISABLED_REASON: str | None = None


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
        return out
    except Exception:
        return []

# Discover trending crypto pairs from Binance
def get_trending_crypto_pairs(top_n=20):
    global _BINANCE_DISABLED_REASON
    provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
    if provider == "cryptocompare":
        return _cryptocompare_top_crypto_pairs(top_n)
    if _BINANCE_DISABLED_REASON is not None:
        # Fallback universe when Binance is blocked.
        return _cryptocompare_top_crypto_pairs(top_n)
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
        return [x['symbol'] for x in sorted_pairs[:top_n]]
    except Exception as e:
        print(f"[WARN] Could not fetch Binance pairs: {e}")
        return _cryptocompare_top_crypto_pairs(top_n)

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
    return crypto + fx

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)
