def momentum_strategies(asset, timeframe, market_data):
    strat = MomentumStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Momentum Strategies ---
class RSIMomentumStrategy(BaseStrategy):
    name = "RSI Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        if ind['rsi'] < 30:
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
        if ind['rsi'] > 70:
            entry = candles[-1]['close']
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SELL',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.7
            }
        return None

class MACDMomentumStrategy(BaseStrategy):
    name = "MACD Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('macd_hist', 0) > 0 and candles:
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

class StochRSIMomentumStrategy(BaseStrategy):
    name = "Stoch RSI Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('stoch_rsi', 0) < 0.2 and candles:
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

def momentum_strategies(asset, timeframe, market_data):
    strategies = [RSIMomentumStrategy(), MACDMomentumStrategy(), StochRSIMomentumStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            signals.append(sig)
    return signals
