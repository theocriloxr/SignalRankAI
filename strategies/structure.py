def structure_strategy(asset, timeframe, market_data):
    """Run structure strategies with stale data consistency check."""
    # PHASE 1 FIX #4: Stale Data Consistency - 24-hour check
    # Verify data is recent (not stale) - last candle should be within reasonable time
    if not market_data or 'candles' not in market_data or 'indicators' not in market_data:
        return []
    
    candles = market_data.get('candles', [])
    if not candles or len(candles) < 20:
        return []  # Insufficient data for reliable signals
    
    # Check data freshness - reject if older than 24 hours
    try:
        from datetime import datetime, timedelta, timezone
        last_ts = candles[-1].get('timestamp', 0)
        if last_ts > 0:
            last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            if datetime.now(timezone.utc) - last_time > timedelta(hours=24):
                return []  # Stale data, skip signal
    except Exception:
        pass  # If timestamp check fails, proceed anyway
    
    strat = StructureStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Structure Strategies ---
class StructureBiasStrategy(BaseStrategy):
    """Renamed from StructureBullStrategy — now handles both LONG and SHORT bias."""
    name = "Structure Bias"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles or not ind.get('ema_trend'):
            return None
        price = candles[-1]['close']
        ema_trend = ind['ema_trend']
        # LONG: price above EMA trend = bullish market structure
        if price > ema_trend:
            stop = candles[-1]['low']
            return {
                'direction': 'LONG',
                'entry': price,
                'stop': stop,
                'targets': price + (price - stop) * 2,
                'confidence': 0.6,
                'reasoning': "Price above EMA trend — bullish market structure LONG."
            }
        # SHORT: price below EMA trend = bearish market structure
        if price < ema_trend:
            stop = candles[-1]['high']
            return {
                'direction': 'SHORT',
                'entry': price,
                'stop': stop,
                'targets': price - (stop - price) * 2,
                'confidence': 0.6,
                'reasoning': "Price below EMA trend — bearish market structure SHORT."
            }
        return None

# Keep old name as alias for backward compatibility
StructureBullStrategy = StructureBiasStrategy

class SRBreakRetestStrategy(BaseStrategy):
    name = "S/R Break + Retest"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        entry = candles[-1]['close']
        # LONG: bullish S/R breakout
        if ind.get('sr_breakout', False):
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.65,
                'reasoning': "Bullish S/R breakout and retest confirmed — LONG."
            }
        # SHORT: bearish S/R breakdown
        if ind.get('sr_breakdown', False):
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.65,
                'reasoning': "Bearish S/R breakdown and retest confirmed — SHORT."
            }
        return None

class LiquiditySweepStrategy(BaseStrategy):
    name = "Liquidity Sweep"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles or not ind.get('liquidity_sweep', False):
            return None
        entry = candles[-1]['close']
        # Direction from sweep type: sweep of lows = bullish reversal (LONG)
        # sweep of highs = bearish reversal (SHORT)
        sweep_dir = str(ind.get('liquidity_sweep_direction', '')).upper()
        if sweep_dir == 'BEARISH' or sweep_dir == 'SELL':
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': 0.6,
                'reasoning': "Bearish liquidity sweep (sweep of highs) — SHORT."
            }
        # Default: sweep of lows = bullish bounce LONG
        stop = candles[-1]['low']
        target = entry + (entry - stop) * 2
        return {
            'direction': 'LONG',
            'entry': entry,
            'stop': stop,
            'targets': target,
            'confidence': 0.6,
            'reasoning': "Bullish liquidity sweep (sweep of lows) — LONG."
        }

def structure_strategy(asset, timeframe, market_data):
    strategies = [StructureBiasStrategy(), SRBreakRetestStrategy(), LiquiditySweepStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            sig['asset'] = asset
            sig['symbol'] = asset
            sig['timeframe'] = timeframe
            sig['strategy_name'] = getattr(strat, 'name', strat.__class__.__name__)
            sig['strategy_group'] = 'structure'
            sig['strength'] = float(sig.get('confidence', 0) or 0)
            sig['volatility'] = float(market_data.get('indicators', {}).get('bollinger', {}).get('width', 0) or 0)
            signals.append(sig)
    return signals
