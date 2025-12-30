
from .base import BaseStrategy

class StructureStrategy(BaseStrategy):
    name = "Structure Bull"

    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['ema_trend'] and candles:
            price = candles[-1]['close']
            if price > ind['ema_trend']:
                signal = {
                    'symbol': market_data['symbol'],
                    'direction': 'BUY',
                    'timeframe': market_data['timeframe'],
                    'entry': price,
                    'stop': candles[-1]['low'],
                    'targets': None,
                    'confidence': 0.6
                }
                return signal
        return None
