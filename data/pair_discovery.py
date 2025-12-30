import ccxt
import requests

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr'
FX_API = 'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&apikey={api_key}'

# Discover trending crypto pairs from Binance
def get_trending_crypto_pairs(top_n=20):
    resp = requests.get(BINANCE_API)
    data = resp.json()
    # Sort by quoteVolume (trending)
    sorted_pairs = sorted(data, key=lambda x: float(x['quoteVolume']), reverse=True)
    return [x['symbol'] for x in sorted_pairs[:top_n]]

# Discover trending FX pairs (placeholder: use your own logic or API)
def get_trending_fx_pairs():
    # Example: hardcoded popular pairs
    return ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD']

# Combine all pairs for strategy engine
def get_all_trending_pairs():
    crypto = get_trending_crypto_pairs()
    fx = get_trending_fx_pairs()
    return crypto + fx

# Example usage:
# pairs = get_all_trending_pairs()
# print(pairs)
