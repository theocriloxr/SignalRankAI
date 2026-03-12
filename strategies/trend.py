from .base import BaseStrategy

# --- Trend Strategies ---
class EMATrendStrategy(BaseStrategy):
    name = "EMA Trend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        # LONG: EMA bullish stack
        if ind['ema_fast'] > ind['ema_slow'] and ind['ema_slow'] > ind['ema_trend']:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.9,
                'reasoning': "EMA fast > EMA slow > EMA trend. Uptrend confirmed — LONG."
            }
        # SHORT: EMA bearish stack
        if ind['ema_fast'] < ind['ema_slow'] and ind['ema_slow'] < ind['ema_trend']:
            entry = candles[-1]['close']
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.9,
                'reasoning': "EMA fast < EMA slow < EMA trend. Downtrend confirmed — SHORT."
            }
        return None

class SupertrendStrategy(BaseStrategy):
    name = "Supertrend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        entry = candles[-1]['close']
        if ind.get('supertrend_signal') == 'BUY':
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.85,
                'reasoning': "Supertrend signals LONG."
            }
        if ind.get('supertrend_signal') == 'SELL':
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.85,
                'reasoning': "Supertrend signals SHORT."
            }
        return None

class ADXTrendStrategy(BaseStrategy):
    name = "ADX Trend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles or ind.get('adx', 0) <= 25:
            return None
        entry = candles[-1]['close']
        # LONG: DI+ > DI- (buyers dominating)
        if ind.get('di_plus', 0) > ind.get('di_minus', 0):
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.8,
                'reasoning': f"ADX {ind.get('adx', 0):.1f} strong, DI+ > DI-. Trend LONG."
            }
        # SHORT: DI- > DI+ (sellers dominating)
        if ind.get('di_minus', 0) > ind.get('di_plus', 0):
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.8,
                'reasoning': f"ADX {ind.get('adx', 0):.1f} strong, DI- > DI+. Trend SHORT."
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
