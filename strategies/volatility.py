import logging

from data.indicator_schema import missing_indicators, normalize_indicator_schema
from .base import BaseStrategy

logger = logging.getLogger(__name__)

# --- Volatility Strategies ---
class ATRBreakoutStrategy(BaseStrategy):
    name = "ATR Breakout"
    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get('indicators') or {})
        candles = market_data.get('candles') or []
        bollinger = ind.get('bollinger') if isinstance(ind.get('bollinger'), dict) else {}
        width = bollinger.get('width') or ind.get('bollinger_width')
        missing = missing_indicators(ind, ("atr",))
        if width in (None, ""):
            missing.append("bollinger.width")
        if not candles or missing:
            logger.debug(
                "%s missing indicators: %s available=%s",
                self.name,
                missing,
                sorted(ind.keys())[:12],
            )
            return None
        atr = float(ind.get('atr') or 0)
        width_f = float(width or 0)
        if atr > 1.5 * width_f and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.8,
                'reasoning': f"ATR breakout: ATR > 1.5x Bollinger width. Volatility surge for BUY."
            }
        return None

class BBWidthVolatilityStrategy(BaseStrategy):
    name = "BB Width Volatility"
    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get('indicators') or {})
        candles = market_data.get('candles') or []
        if ind.get('bollinger_width', 0) > 0.05 and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.75,
                'reasoning': f"Bollinger width > 0.05. Volatility expansion for BUY."
            }
        return None

class KeltnerVolatilityStrategy(BaseStrategy):
    name = "Keltner Volatility"
    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get('indicators') or {})
        candles = market_data.get('candles') or []
        if ind.get('keltner_width', 0) > 0.04 and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.7,
                'reasoning': f"Keltner width > 0.04. Volatility signal for BUY."
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
