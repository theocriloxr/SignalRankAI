def trend_strategies(asset, timeframe, market_data):
    # Returns a list of signals from all trend strategies for the given asset/timeframe
    strat = TrendStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Trend Strategies ---
class EMATrendStrategy(BaseStrategy):
    name = "EMA Trend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['ema_fast'] > ind['ema_slow'] and ind['ema_slow'] > ind['ema_trend']:
            if candles:
                entry = candles[-1]['close']
                stop = candles[-1]['low']
                target = entry + (entry - stop) * 2
                return {
                    'direction': 'BUY',
                    'entry': entry,
                    'stop': stop,
                    'targets': target,
                    'confidence': 0.9
                }
        return None

class SupertrendStrategy(BaseStrategy):
    name = "Supertrend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('supertrend_signal') == 'BUY' and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.85
            }
        return None

class ADXTrendStrategy(BaseStrategy):
    name = "ADX Trend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('adx', 0) > 25 and ind.get('di_plus', 0) > ind.get('di_minus', 0) and candles:
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

def trend_strategies(asset, timeframe, market_data):
    strategies = [EMATrendStrategy(), SupertrendStrategy(), ADXTrendStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            sig['asset'] = asset
            sig['symbol'] = asset
            sig['timeframe'] = timeframe
            sig['strategy_name'] = getattr(strat, 'name', strat.__class__.__name__)
            sig['strategy_group'] = 'trend'
            sig['strength'] = float(sig.get('confidence', 0) or 0)
            sig['volatility'] = float(market_data.get('indicators', {}).get('bollinger', {}).get('width', 0) or 0)
            signals.append(sig)
    return signals
