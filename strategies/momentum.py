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
            return {
                'symbol': market_data['symbol'],
                'direction': 'BUY',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['low'],
                'targets': None,
                'confidence': 0.7
            }
        if ind['rsi'] > 70:
            return {
                'symbol': market_data['symbol'],
                'direction': 'SELL',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['high'],
                'targets': None,
                'confidence': 0.7
            }
        return None

class MACDMomentumStrategy(BaseStrategy):
    name = "MACD Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('macd_hist', 0) > 0 and candles:
            return {
                'symbol': market_data['symbol'],
                'direction': 'BUY',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['low'],
                'targets': None,
                'confidence': 0.75
            }
        return None

class StochRSIMomentumStrategy(BaseStrategy):
    name = "Stoch RSI Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('stochrsi', 0) < 0.2 and candles:
            return {
                'symbol': market_data['symbol'],
                'direction': 'BUY',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['low'],
                'targets': None,
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
