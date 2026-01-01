import os
import ccxt
import requests

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

# Discover trending crypto pairs from Binance
def get_trending_crypto_pairs(top_n=20):
    try:
        resp = requests.get(BINANCE_API, timeout=5)
        data = resp.json()
        # Sort by quoteVolume (trending)
        sorted_pairs = sorted(data, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [x['symbol'] for x in sorted_pairs[:top_n]]
    except Exception as e:
        print(f"[WARN] Could not fetch Binance pairs: {e}")
        return []

def get_trending_fx_pairs():
    """Return configured FX pairs.

    This avoids hardcoded demo pairs. Configure via FX_PAIRS (comma-separated), e.g.
    FX_PAIRS="EURUSD,GBPUSD,USDJPY".
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
