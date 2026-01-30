from strategies.momentum import momentum_strategies
from strategies.structure import structure_strategy
from strategies.trend import trend_strategies

def best_crypto_strategies(asset, market_data, regime):
    # Use a blend of momentum, structure, and trend strategies for crypto
    signals = []
    signals += momentum_strategies(asset, '1h', market_data)
    signals += structure_strategy(asset, '1h', market_data)
    signals += trend_strategies(asset, '1h', market_data)
    return [s for s in signals if s]
