
from .base import BaseStrategy

class TrendStrategy(BaseStrategy):
    name = "EMA Trend"

    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['ema_fast'] > ind['ema_slow'] and ind['ema_slow'] > ind['ema_trend']:
            if candles:
                signal = {
                    'symbol': market_data['symbol'],
                    'direction': 'BUY',
                    'timeframe': market_data['timeframe'],
                    'entry': candles[-1]['close'],
                    'stop': candles[-1]['low'],
                    'targets': None,
                    'confidence': 0.9
                }
                return signal
        return None
