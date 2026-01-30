def best_stock_strategies(asset, market_data, regime):
    # Use the best available stock strategies (example: SMA crossover)
    return stock_strategies(asset, '1h', market_data)
from .base import BaseStrategy

def stock_trend_strategy(asset, timeframe, market_data):
    ind = market_data.get('indicators', {})
    candles = market_data.get('candles', [])
    if not candles:
        return None
    # Example: Simple moving average crossover
    sma_fast = ind.get('sma_fast', 0)
    sma_slow = ind.get('sma_slow', 0)
    if sma_fast > sma_slow:
        entry = candles[-1]['close']
        stop = candles[-1]['low']
        target = entry + (entry - stop) * 2
        return {
            'direction': 'BUY',
            'entry': entry,
            'stop': stop,
            'targets': target,
            'confidence': 0.8,
            'reasoning': "SMA fast > SMA slow. Uptrend for BUY."
        }
    elif sma_fast < sma_slow:
        entry = candles[-1]['close']
        stop = candles[-1]['high']
        target = entry - (stop - entry) * 2
        return {
            'direction': 'SELL',
            'entry': entry,
            'stop': stop,
            'targets': target,
            'confidence': 0.8,
            'reasoning': "SMA fast < SMA slow. Downtrend for SELL."
        }
    return None

def stock_strategies(asset, timeframe, market_data):
    strategies = [stock_trend_strategy]
    signals = []
    for strat in strategies:
        sig = strat(asset, timeframe, market_data)
        if sig:
            sig['asset'] = asset
            sig['symbol'] = asset
            sig['timeframe'] = timeframe
            sig['strategy_name'] = strat.__name__
            sig['strategy_group'] = 'stock'
            sig['strength'] = float(sig.get('confidence', 0) or 0)
            signals.append(sig)
    return signals
