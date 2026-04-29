from .base import BaseStrategy
from .dynamic_targets import calculate_dynamic_targets


def momentum_strategies(asset, timeframe, market_data):
    """Run all momentum strategies with dynamic targets and confirmation filters."""
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
    
    # Run all momentum strategies
    strategies = [
        RSIMomentumStrategy(),
        MACDMomentumStrategy(),
        StochRSIMomentumStrategy()
    ]
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
        regime = ind.get('regime', 'neutral')
        
        # BUY: RSI oversold (<30) with MACD histogram positive (momentum building)
        if rsi < 30:
            # Confirmation: MACD histogram should be positive or just turned positive
            if macd_hist < -0.0001:  # MACD histogram still negative = false signal, skip
                return None
            entry = candles[-1]['close']
            confidence = 0.65 + (0.20 * (1 - max(0, min(rsi, 30)) / 30))
            
            # Use dynamic targets instead of fixed static values
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"RSI ({rsi:.1f}) oversold, MACD histogram positive. Momentum building for LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SELL: RSI overbought (>70) with MACD histogram negative (momentum fading)
        if rsi > 70:
            # Confirmation: MACD histogram should be negative or just turned negative
            if macd_hist > 0.0001:  # MACD histogram still positive = false signal, skip
                return None
            entry = candles[-1]['close']
            confidence = 0.65 + (0.20 * ((rsi - 70) / 30))
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"RSI ({rsi:.1f}) overbought, MACD histogram negative. Momentum fading for SHORT. R:R={levels['rr_ratio']:.2f}"
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
        regime = ind.get('regime', 'neutral')
        
        # BUY: MACD histogram positive AND RSI above 40 (not oversold, but building momentum)
        if macd_hist > 0.0001:
            if rsi < 35:  # RSI too low = might be false signal in reversal
                return None
            entry = candles[-1]['close']
            confidence = min(0.85, 0.55 + abs(macd_hist) / 10)
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"MACD histogram positive ({macd_hist:.4f}), RSI ({rsi:.1f}) confirms momentum for LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SELL: MACD histogram negative AND RSI below 60 (not overbought, but losing momentum)
        if macd_hist < -0.0001:
            if rsi > 65:  # RSI too high = might be false signal in reversal
                return None
            entry = candles[-1]['close']
            confidence = min(0.85, 0.55 + abs(macd_hist) / 10)
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"MACD histogram negative ({macd_hist:.4f}), RSI ({rsi:.1f}) confirms momentum for SHORT. R:R={levels['rr_ratio']:.2f}"
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
        regime = ind.get('regime', 'neutral')
        
        # BUY: Stoch RSI oversold (<0.2) AND price above EMA (in uptrend)
        if stoch_rsi < 0.2:
            price = candles[-1]['close']
            # Confirmation: price should be above 20-EMA (in uptrend context)
            if ema_fast > 0 and price < ema_fast:
                return None  # Price below EMA = not in uptrend
            entry = price
            confidence = 0.60 + (0.25 * (1 - stoch_rsi / 0.2))  # Range 0.60-0.85
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=min(0.85, confidence)
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': min(0.85, confidence),
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Stoch RSI ({stoch_rsi:.2f}) oversold, price above EMA. Bounce trade for LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SELL: Stoch RSI overbought (>0.8) AND price below EMA (in downtrend)
        if stoch_rsi > 0.8:
            price = candles[-1]['close']
            # Confirmation: price should be below 20-EMA (in downtrend context)
            if ema_fast > 0 and price > ema_fast:
                return None  # Price above EMA = not in downtrend
            entry = price
            confidence = 0.60 + (0.25 * ((stoch_rsi - 0.8) / 0.2))  # Range 0.60-0.85
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=min(0.85, confidence)
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': min(0.85, confidence),
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Stoch RSI ({stoch_rsi:.2f}) overbought, price below EMA. Reversal trade for SHORT. R:R={levels['rr_ratio']:.2f}"
            }
        return None

