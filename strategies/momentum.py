def momentum_strategies(asset, timeframe, market_data):
    # Validate real-time data integrity
    if not market_data or 'candles' not in market_data or 'indicators' not in market_data:
        return []
    
    candles = market_data.get('candles', [])
    if not candles or len(candles) < 20:
        return []  # Insufficient data for reliable signals
    
    # Verify data is recent (not stale) - last candle should be within reasonable time
    try:
        from datetime import datetime, timedelta, timezone
        last_ts = candles[-1].get('timestamp', 0)
        if last_ts > 0:
            last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            # Data older than 24 hours = stale
            if datetime.now(timezone.utc) - last_time > timedelta(hours=24):
                return []  # Stale data, skip signal
    except Exception:
        pass  # If timestamp check fails, proceed anyway but log it
    
    strat = MomentumStrategy()
    signal = strat.evaluate(market_data)
    return [signal] if signal else []


from .base import BaseStrategy

# --- Momentum Strategies ---
class RSIMomentumStrategy(BaseStrategy):
    """RSI oversold/overbought with MACD confirmation for better accuracy."""
    name = "RSI Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        
        rsi = float(ind.get('rsi', 50))
        macd_hist = float(ind.get('macd_hist', 0))
        
        # BUY: RSI oversold (<30) with MACD histogram positive (momentum building)
        if rsi < 30:
            # Confirmation: MACD histogram should be positive or just turned positive
            if macd_hist < -0.0001:  # MACD histogram still negative = false signal, skip
                return None
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            confidence = 0.65 + (0.20 * (1 - max(0, min(rsi, 30)) / 30))
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': confidence,
                'reasoning': f"RSI ({rsi:.1f}) oversold, MACD histogram positive. Momentum building for BUY."
            }
        
        # SELL: RSI overbought (>70) with MACD histogram negative (momentum fading)
        if rsi > 70:
            # Confirmation: MACD histogram should be negative or just turned negative
            if macd_hist > 0.0001:  # MACD histogram still positive = false signal, skip
                return None
            entry = candles[-1]['close']
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            confidence = 0.65 + (0.20 * ((rsi - 70) / 30))
            return {
                'direction': 'SELL',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': confidence,
                'reasoning': f"RSI ({rsi:.1f}) overbought, MACD histogram negative. Momentum fading for SELL."
            }
        return None

class MACDMomentumStrategy(BaseStrategy):
    """MACD histogram crossover with RSI confirmation."""
    name = "MACD Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        
        macd_hist = float(ind.get('macd_hist', 0))
        rsi = float(ind.get('rsi', 50))
        
        # BUY: MACD histogram positive AND RSI above 40 (not oversold, but building momentum)
        if macd_hist > 0.0001:
            if rsi < 35:  # RSI too low = might be false signal in reversal
                return None
            entry = candles[-1]['close']
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            macd_confidence = min(0.85, 0.55 + abs(macd_hist) / 10)
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': macd_confidence,
                'reasoning': f"MACD histogram positive ({macd_hist:.4f}), RSI ({rsi:.1f}) confirms momentum for BUY."
            }
        
        # SELL: MACD histogram negative AND RSI below 60 (not overbought, but losing momentum)
        if macd_hist < -0.0001:
            if rsi > 65:  # RSI too high = might be false signal in reversal
                return None
            entry = candles[-1]['close']
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            macd_confidence = min(0.85, 0.55 + abs(macd_hist) / 10)
            return {
                'direction': 'SELL',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': macd_confidence,
                'reasoning': f"MACD histogram negative ({macd_hist:.4f}), RSI ({rsi:.1f}) confirms momentum for SELL."
            }
        return None

class StochRSIMomentumStrategy(BaseStrategy):
    """Stochastic RSI with moving average confirmation for bounce trades."""
    name = "Stoch RSI Momentum"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        
        stoch_rsi = float(ind.get('stoch_rsi', 0.5))
        rsi = float(ind.get('rsi', 50))
        ema_fast = float(ind.get('ema_fast', 0) or 0)
        ema_slow = float(ind.get('ema_slow', 0) or 0)
        
        # BUY: Stoch RSI oversold (<0.2) AND price above EMA (in uptrend)
        if stoch_rsi < 0.2:
            price = candles[-1]['close']
            # Confirmation: price should be above 20-EMA (in uptrend context)
            if ema_fast > 0 and price < ema_fast:
                return None  # Price below EMA = not in uptrend
            entry = price
            stop = candles[-1]['low']
            target = entry + (entry - stop) * 2
            confidence = 0.60 + (0.25 * (1 - stoch_rsi / 0.2))  # Range 0.60-0.85
            return {
                'direction': 'BUY',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': min(0.85, confidence),
                'reasoning': f"Stoch RSI ({stoch_rsi:.2f}) oversold, price above EMA. Bounce trade for BUY."
            }
        
        # SELL: Stoch RSI overbought (>0.8) AND price below EMA (in downtrend)
        if stoch_rsi > 0.8:
            price = candles[-1]['close']
            # Confirmation: price should be below 20-EMA (in downtrend context)
            if ema_fast > 0 and price > ema_fast:
                return None  # Price above EMA = not in downtrend
            entry = price
            stop = candles[-1]['high']
            target = entry - (stop - entry) * 2
            confidence = 0.60 + (0.25 * ((stoch_rsi - 0.8) / 0.2))  # Range 0.60-0.85
            return {
                'direction': 'SELL',
                'entry': entry,
                'stop': stop,
                'targets': target,
                'confidence': min(0.85, confidence),
                'reasoning': f"Stoch RSI ({stoch_rsi:.2f}) overbought, price below EMA. Reversal trade for SELL."
            }
        return None

def momentum_strategies(asset, timeframe, market_data):
    """Run all momentum strategies with confirmation filters."""
    strategies = [RSIMomentumStrategy(), MACDMomentumStrategy(), StochRSIMomentumStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            sig['asset'] = asset
            sig['symbol'] = asset
            sig['timeframe'] = timeframe
            sig['strategy_name'] = getattr(strat, 'name', strat.__class__.__name__)
            sig['strategy_group'] = 'momentum'
            sig['strength'] = float(sig.get('confidence', 0) or 0)
            sig['volatility'] = float(market_data.get('indicators', {}).get('bollinger', {}).get('width', 0) or 0)
            signals.append(sig)
    return signals

