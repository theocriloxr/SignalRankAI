from .base import BaseStrategy
from .dynamic_targets import calculate_dynamic_targets

# --- Trend Strategies ---
class EMATrendStrategy(BaseStrategy):
    name = "EMA Trend"
    def evaluate(self, market_data):
        ind = market_data['indicators']
        candles = market_data['candles']
        if not candles:
            return None
        
        # Use available EMA indicator with fallback to ema_50 or trend_ema
        ema_trend = ind.get('ema_trend') or ind.get('ema_50') or ind.get('trend_ema') or 0
        if not ema_trend:
            return None
            
        # LONG: EMA bullish stack
        if ind['ema_fast'] > ind['ema_slow'] and ind['ema_slow'] > ema_trend:
            entry = candles[-1]['close']
            regime = ind.get('regime', 'neutral')
            quality = 0.9  # High confidence for strong EMA alignment
            
            # Use dynamic targets instead of fixed static values
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"EMA fast > EMA slow > EMA trend. Uptrend confirmed — LONG. R:R={levels['rr_ratio']:.2f}"
            }
# SHORT: EMA bearish stack
        if ind['ema_fast'] < ind['ema_slow'] and ind['ema_slow'] < ema_trend:
            entry = candles[-1]['close']
            regime = ind.get('regime', 'neutral')
            quality = 0.9
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"EMA fast < EMA slow < EMA trend. Downtrend confirmed — SHORT. R:R={levels['rr_ratio']:.2f}"
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
        regime = ind.get('regime', 'neutral')
        
        if ind.get('supertrend_signal') == 'BUY':
            quality = 0.85
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Supertrend signals LONG. R:R={levels['rr_ratio']:.2f}"
            }
        if ind.get('supertrend_signal') == 'SELL':
            quality = 0.85
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"Supertrend signals SHORT. R:R={levels['rr_ratio']:.2f}"
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
        regime = ind.get('regime', 'neutral')
        
        # LONG: DI+ > DI- (buyers dominating)
        if ind.get('di_plus', 0) > ind.get('di_minus', 0):
            quality = 0.8
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='LONG',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'LONG',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"ADX {ind.get('adx', 0):.1f} strong, DI+ > DI-. Trend LONG. R:R={levels['rr_ratio']:.2f}"
            }
        # SHORT: DI- > DI+ (sellers dominating)
        if ind.get('di_minus', 0) > ind.get('di_plus', 0):
            quality = 0.8
            
            # Use dynamic targets
            levels = calculate_dynamic_targets(
                direction='SHORT',
                entry_price=entry,
                candles=candles,
                indicators=ind,
                regime=regime,
                signal_quality=quality
            )
            
            return {
                'direction': 'SHORT',
                'entry': entry,
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                'targets': levels['tp_levels'],
                'confidence': quality,
                'rr_ratio': levels['rr_ratio'],
                'reasoning': f"ADX {ind.get('adx', 0):.1f} strong, DI- > DI+. Trend SHORT. R:R={levels['rr_ratio']:.2f}"
            }
        return None

def trend_strategies(asset, timeframe, market_data):
    """Run all trend strategies with stale data consistency check."""
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
