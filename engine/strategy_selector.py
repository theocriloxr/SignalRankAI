from strategies.crypto import best_crypto_strategies
from strategies.fx import best_fx_strategies
from strategies.stock import best_stock_strategies
from strategies.commodity import best_commodity_strategies
from data.fetcher import is_crypto, is_fx, is_stock, is_commodity

def get_best_strategies_for_asset(asset):
    if is_crypto(asset):
        return best_crypto_strategies
    elif is_fx(asset):
        return best_fx_strategies
    elif is_stock(asset):
        return best_stock_strategies
    elif is_commodity(asset):
        return best_commodity_strategies
    else:
        return []
