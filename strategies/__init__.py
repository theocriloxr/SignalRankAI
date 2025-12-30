from .trend import trend_strategies
from .momentum import momentum_strategies
from .volatility import volatility_strategies
from .structure import structure_strategy

def run_all_strategies(asset, market_data, regime):
    signals = []
    for timeframe, data in market_data.items():
        if regime == "TRENDING":
            signals += trend_strategies(asset, timeframe, data)
        if regime == "RANGING":
            signals += momentum_strategies(asset, timeframe, data)
        if regime == "VOLATILE":
            signals += volatility_strategies(asset, timeframe, data)
        signals += structure_strategy(asset, timeframe, data)
    return signals
