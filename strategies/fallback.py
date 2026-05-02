"""
Simple Fallback Strategies - Designed to generate signals when main strategies fail.

These strategies use relaxed conditions and basic price action to ensure
the engine produces signals even in challenging market conditions.

Key differences from main strategies:
- No multi-indicator stacking requirements
- Works with single indicator confirmation
- Relaxed thresholds (e.g., ADX > 20 instead of 25)
- Basic price action + volume confirmation
"""

from .base import BaseStrategy
from .dynamic_targets import calculate_dynamic_targets


def fallback_strategies(asset, timeframe, market_data):
    """
    Run fallback strategies with relaxed conditions.
    These should generate signals when main strategies produce nothing.
    """
    if not market_data or 'candles' not in market_data or 'indicators' not in market_data:
        return []
    
    candles = market_data.get('candles', [])
    if not candles or len(candles) < 20:
        return []
    
    strategies = [
        SimplePriceActionStrategy(),       # Basic price vs SMA
        SimpleVolumeConfirmationStrategy(), # Volume spike confirmation
        SimpleTrendContinuationStrategy(),  # Trend continuation
        SimpleRangeBreakStrategy(),         # Range/flat breakout
    ]
    
    signals = []
    for strat in strategies:
        try:
            sig = strat.evaluate(market_data)
            if sig:
                sig['asset'] = asset
                sig['symbol'] = asset
                sig['timeframe'] = timeframe
                sig['strategy_name'] = getattr(strat, 'name', strat.__class__.__name__)
                sig['strategy_group'] = 'fallback'
                sig['is_fallback'] = True  # Mark as fallback for quality tracking
                sig['strength'] = float(sig.get('confidence', 0) or 0)
                sig['volatility'] = float(market_data.get('indicators', {}).get('bollinger', {}).get('width', 0) or 0)
                signals.append(sig)
        except Exception as e:
            # Don't let one strategy failure break entire group
            pass
    
    return signals


class SimplePriceActionStrategy(BaseStrategy):
    """
    Simple price action: price above/below 20-period SMA with candle confirmation.
    This is the most basic trend-following signal.
    """
    name = "Simple Price Action"
    
    def evaluate(self, market_data):
        ind = market_data.get('indicators', {})
        candles = market_data.get('candles', [])
        if not candles or len(candles) < 20:
            return None
        
        close = candles[-1]['close']
        open_price = candles[-1].get('open', close)
        sma_20 = ind.get('sma_20')
        
        # Need SMA for comparison
        if sma_20 is None or sma_20 <= 0:
            return None
        
        regime = ind.get('regime', 'neutral')
        
        # LONG: Price above SMA20 AND green candle (close > open)
        if close > sma_20 and close > open_price:
            confidence = 0.55  # Lower confidence since simple
            
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Price {close:.4f} above SMA20 {sma_20:.4f}, green candle. Basic trend follow. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SHORT: Price below SMA20 AND red candle (close < open)
        if close < sma_20 and close < open_price:
            confidence = 0.55
            
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Price {close:.4f} below SMA20 {sma_20:.4f}, red candle. Basic trend follow. R:R={levels['rr_ratio']:.2f}"
            }
        
        return None


class SimpleVolumeConfirmationStrategy(BaseStrategy):
    """
    Volume spike + price move in same direction.
    High volume with price movement = higher conviction.
    """
    name = "Simple Volume Confirmation"
    
    def evaluate(self, market_data):
        ind = market_data.get('indicators', {})
        candles = market_data.get('candles', [])
        if not candles or len(candles) < 20:
            return None
        
        close = candles[-1]['close']
        open_price = candles[-1].get('open', close)
        volume_ratio = ind.get('volume_ratio', 1.0)
        volume = ind.get('volume', 0)
        volume_avg = ind.get('volume_avg', 1)
        
        # Skip if volume data unavailable
        if volume_avg is None or volume_avg <= 0:
            return None
        
        regime = ind.get('regime', 'neutral')
        
        # LONG: Green candle with above-average volume
        if close > open_price and volume_ratio > 1.2:
            confidence = min(0.70, 0.50 + (volume_ratio - 1.0) * 0.2)
            
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Green candle + volume {volume_ratio:.1f}x avg. Volume confirmation LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SHORT: Red candle with above-average volume
        if close < open_price and volume_ratio > 1.2:
            confidence = min(0.70, 0.50 + (volume_ratio - 1.0) * 0.2)
            
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Red candle + volume {volume_ratio:.1f}x avg. Volume confirmation SHORT. R:R={levels['rr_ratio']:.2f}"
            }
        
        return None


class SimpleTrendContinuationStrategy(BaseStrategy):
    """
    Simple trend continuation using EMA crossover (faster vs slower EMA).
    More relaxed than full EMA stack requirement.
    """
    name = "Simple Trend Continuation"
    
    def evaluate(self, market_data):
        ind = market_data.get('indicators', {})
        candles = market_data.get('candles', [])
        if not candles or len(candles) < 20:
            return None
        
        close = candles[-1]['close']
        ema_fast = ind.get('ema_fast', 0)
        ema_slow = ind.get('ema_slow', 0)
        
        # Need both EMAs
        if ema_fast <= 0 or ema_slow <= 0:
            return None
        
        regime = ind.get('regime', 'neutral')
        
        # LONG: Fast EMA above slow EMA (simple bullish alignment)
        if ema_fast > ema_slow:
            # Additional confirmation: price above fast EMA (stronger signal)
            strength_factor = 0.10 if close > ema_fast else 0.0
            confidence = min(0.65, 0.50 + strength_factor)
            
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"EMA{12} {ema_fast:.4f} > EMA{26} {ema_slow:.4f}. Trend continuation LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SHORT: Fast EMA below slow EMA (simple bearish alignment)
        if ema_fast < ema_slow:
            strength_factor = 0.10 if close < ema_fast else 0.0
            confidence = min(0.65, 0.50 + strength_factor)
            
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"EMA{12} {ema_fast:.4f} < EMA{26} {ema_slow:.4f}. Trend continuation SHORT. R:R={levels['rr_ratio']:.2f}"
            }
        
        return None


class SimpleRangeBreakStrategy(BaseStrategy):
    """
    Simple range breakout - price breaking 20-period high/low.
    Works in ranging markets when price breaks consolidation.
    """
    name = "Simple Range Break"
    
    def evaluate(self, market_data):
        ind = market_data.get('indicators', {})
        candles = market_data.get('candles', [])
        if not candles or len(candles) < 20:
            return None
        
        close = candles[-1]['close']
        
        # Calculate simple 20-period range
        highs = [c.get('high', 0) for c in candles[-20:] if c.get('high')]
        lows = [c.get('low', 0) for c in candles[-20:] if c.get('low')]
        
        if not highs or not lows:
            return None
        
        high_20 = max(highs)
        low_20 = min(lows)
        
        # Skip if range is too tight (no clear breakout potential)
        range_pct = (high_20 - low_20) / low_20 if low_20 > 0 else 0
        if range_pct < 0.005:  # Less than 0.5% range = too tight
            return None
        
        regime = ind.get('regime', 'neutral')
        
        # LONG: Break above 20-period high
        if close > high_20:
            confidence = min(0.70, 0.55 + range_pct)  # Larger range = higher confidence
            
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'LONG',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Breakout above 20h high {high_20:.4f}. Range break LONG. R:R={levels['rr_ratio']:.2f}"
            }
        
        # SHORT: Break below 20-period low
        if close < low_20:
            confidence = min(0.70, 0.55 + range_pct)
            
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=close,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=confidence
            )
            
            return {
                'direction': 'SHORT',
                'entry': close,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': confidence,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Breakdown below 20h low {low_20:.4f}. Range break SHORT. R:R={levels['rr_ratio']:.2f}"
            }
        
        return None
