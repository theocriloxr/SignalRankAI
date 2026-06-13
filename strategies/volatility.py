def volatility_strategies(asset, timeframe, market_data):
    strat = VolatilityStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Volatility Strategies ---
class ATRBreakoutStrategy(BaseStrategy):
    name = "ATR Breakout"
    def evaluate(self, market_data):
        ind = market_data.get('indicators') or {}
        candles = market_data.get('candles') or []
        
        # Use available indicators with fallbacks
        atr = ind.get('atr') or 0
        bb = ind.get('bollinger') or {}
        bb_width = bb.get('width') if bb else (ind.get('bollinger_width') or ind.get('bb_width') or 0)
        
        if not candles or not atr or not bb_width:
            return None
            
        if atr > 1.5 * bb_width:
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
        ind = market_data.get('indicators') or {}
        candles = market_data.get('candles') or []
        
        bb_width = ind.get('bollinger_width') or ind.get('bb_width') or 0
        
        if not candles or bb_width <= 0.05:
            return None
            
        entry = candles[-1]['close']
        stop = candles[-1]['low']
        target = entry + (entry - stop) * 2
        return {
            'direction': 'BUY',
            'entry': entry,
            'stop': stop,
            'targets': target,
            'confidence': 0.75,
            'reasoning': f"Bollinger width {bb_width:.4f} > 0.05. Volatility expansion for BUY."
        }

class KeltnerVolatilityStrategy(BaseStrategy):
    name = "Keltner Volatility"
    def evaluate(self, market_data):
        ind = market_data.get('indicators') or {}
        candles = market_data.get('candles') or []
        
        kelt_width = ind.get('keltner_width') or ind.get('kc_width') or 0
        
        if not candles or kelt_width <= 0.04:
            return None
            
        entry = candles[-1]['close']
        stop = candles[-1]['low']
        target = entry + (entry - stop) * 2
        return {
            'direction': 'BUY',
            'entry': entry,
            'stop': stop,
            'targets': target,
            'confidence': 0.7,
            'reasoning': f"Keltner width {kelt_width:.4f} > 0.04. Volatility signal for BUY."
        }

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
