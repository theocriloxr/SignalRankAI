def structure_strategy(asset, timeframe, market_data):
    strat = StructureStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Structure Strategies ---
class StructureBullStrategy(BaseStrategy):
    name = "Structure Bull"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind['ema_trend'] and candles:
            price = candles[-1]['close']
            if price > ind['ema_trend']:
                return {
                    'direction': 'BUY',
                    'entry': price,
                    'stop': candles[-1]['low'],
                    'targets': price + (price - candles[-1]['low']) * 2,
                    'confidence': 0.6
                }
        return None

class SRBreakRetestStrategy(BaseStrategy):
    name = "S/R Break + Retest"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('sr_breakout', False) and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.65
            }
        return None

class LiquiditySweepStrategy(BaseStrategy):
    name = "Liquidity Sweep"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if ind.get('liquidity_sweep', False) and candles:
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.6
            }
        return None

def structure_strategy(asset, timeframe, market_data):
    strategies = [StructureBullStrategy(), SRBreakRetestStrategy(), LiquiditySweepStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            signals.append(sig)
    return signals
