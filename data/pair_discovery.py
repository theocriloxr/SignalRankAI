import os
import requests

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

_BINANCE_DISABLED_REASON: str | None = None

# Discover trending crypto pairs from Binance
def get_trending_crypto_pairs(top_n=20):
    global _BINANCE_DISABLED_REASON
    if _BINANCE_DISABLED_REASON is not None:
        return []
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
                return []
            raise RuntimeError(f"Binance API error: code={code} msg={msg}")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Binance API response type: {type(data).__name__}")
        # Sort by quoteVolume (trending)
        sorted_pairs = sorted(data, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [x['symbol'] for x in sorted_pairs[:top_n]]
    except Exception as e:
        print(f"[WARN] Could not fetch Binance pairs: {e}")
        return []

def get_trending_fx_pairs():
    """Return configured FX pairs.

    FX pairs are optional and must be explicitly configured.

    Configure via FX_PAIRS (comma-separated), e.g. FX_PAIRS="EURUSD,GBPUSD,USDJPY".
    """
    raw = (os.getenv("FX_PAIRS") or "").strip()
    if not raw:
        return []
    return [x.strip().upper() for x in raw.split(",") if x.strip()]

# Combine all pairs for strategy engine
def get_all_trending_pairs():
    try:
        top_n = int((os.getenv("CRYPTO_TRENDING_TOP_N") or "10").strip())
    except Exception:
        top_n = 10
    crypto = get_trending_crypto_pairs(top_n=max(1, top_n))
    fx = get_trending_fx_pairs()
    return crypto + fx

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)
