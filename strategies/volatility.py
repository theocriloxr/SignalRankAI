
from .base import BaseStrategy

class VolatilityStrategy(BaseStrategy):
    name = "ATR Breakout"

    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['atr'] > 1.5 * ind['bollinger']['width']:
            if candles:
                signal = {
                    'symbol': market_data['symbol'],
                    'direction': 'BUY',
                    'timeframe': market_data['timeframe'],
                    'entry': candles[-1]['close'],
                    'stop': candles[-1]['low'],
                    'targets': None,
                    'confidence': 0.8
                }
                return signal
        return None
