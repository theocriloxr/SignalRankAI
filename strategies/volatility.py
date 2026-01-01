def volatility_strategies(asset, timeframe, market_data):
    strat = VolatilityStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Volatility Strategies ---
class ATRBreakoutStrategy(BaseStrategy):
    name = "ATR Breakout"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['atr'] > 1.5 * ind['bollinger']['width'] and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.8
            }
        return None

class BBWidthVolatilityStrategy(BaseStrategy):
    name = "BB Width Volatility"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('bollinger_width', 0) > 0.05 and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.75
            }
        return None

class KeltnerVolatilityStrategy(BaseStrategy):
    name = "Keltner Volatility"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('keltner_width', 0) > 0.04 and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.7
            }
        return None

def volatility_strategies(asset, timeframe, market_data):
    strategies = [ATRBreakoutStrategy(), BBWidthVolatilityStrategy(), KeltnerVolatilityStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            sig['asset'] = asset
            sig['symbol'] = asset
            sig['timeframe'] = timeframe
            sig['strategy_name'] = getattr(strat, 'name', strat.__class__.__name__)
            sig['strategy_group'] = 'volatility'
            sig['strength'] = float(sig.get('confidence', 0) or 0)
            sig['volatility'] = float(market_data.get('indicators', {}).get('bollinger', {}).get('width', 0) or 0)
            signals.append(sig)
    return signals
