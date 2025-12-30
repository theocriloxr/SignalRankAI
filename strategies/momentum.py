
from .base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    name = "RSI Momentum"

    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        if ind['rsi'] < 30:
            signal = {
                'symbol': market_data['symbol'],
                'direction': 'BUY',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['low'],
                'targets': None,
                'confidence': 0.7
            }
            return signal
        if ind['rsi'] > 70:
            signal = {
                'symbol': market_data['symbol'],
                'direction': 'SELL',
                'timeframe': market_data['timeframe'],
                'entry': candles[-1]['close'],
                'stop': candles[-1]['high'],
                'targets': None,
                'confidence': 0.7
            }
            return signal
        return None
