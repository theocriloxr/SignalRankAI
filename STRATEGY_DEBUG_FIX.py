"""
Signal Generation Debug and Fix - v1.1

This file adds urgent fixes to ensure the engine generates signals.
The main issue is strategy_signals=0 across all assets - need to force signal generation.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def force_emergency_signals(asset, market_data, regime=None):
    """
    ULTRA-FALLBACK: Emergency signal generation that ALWAYS fires
    if there's ANY valid price data. This is the safety net.
    
    This solves the "generated_signals=0" issue by ensuring at least
    basic signals ALWAYS exist when price data is available.
    """
    signals = []
    
    if not market_data or not isinstance(market_data, dict):
        return signals
    
    # Get any available timeframe data
    tf_data = None
    timeframe = None
    for tf in ['1h', '4h', '1d', '15m', '5m']:
        if tf in market_data and market_data[tf]:
            tf_data = market_data[tf]
            timeframe = tf
            break
    
    if not tf_data or not isinstance(tf_data, dict):
        logger.warning(f"[emergency] No timeframe data for {asset}")
        return signals
    
    candles = tf_data.get('candles', [])
    if not candles or len(candles) < 5:
        logger.warning(f"[emergency] Insufficient candles for {asset}: {len(candles) if candles else 0}")
        return signals
    
    # Get indicators
    ind = tf_data.get('indicators', {})
    if not ind:
        logger.warning(f"[emergency] No indicators for {asset}")
        return signals
    
    # Get price data
    close = float(candles[-1].get('close', 0))
    open_price = float(candles[-1].get('open', close))
    high = float(candles[-1].get('high', close))
    low = float(candles[-1].get('low', close))
    
    if close <= 0:
        logger.warning(f"[emergency] Invalid close price for {asset}: {close}")
        return signals
    
    # Get any available average
    sma_20 = ind.get('sma_20') or ind.get('ema_20') or close
    ema_fast = ind.get('ema_fast') or ind.get('ema_12') or close
    ema_slow = ind.get('ema_slow') or ind.get('ema_26') or close
    
    # Calculate dynamic targets
    atr = float(ind.get('atr', 0) or 0)
    if atr <= 0:
        # Calculate basic ATR if missing
        if len(candles) >= 14:
            highs = [c.get('high', 0) for c in candles[-14:]]
            lows = [c.get('low', float('inf')) for c in candles[-14:]]
            closes = [c.get('close', 0) for c in candles[-14:]]
            trs = []
            for i in range(1, len(candles)):
                h = highs[i] if i < len(highs) else close
                l = lows[i] if i < len(lows) else close
                pc = closes[i-1] if i > 0 else close
                tr = max(h - l, abs(h - pc), abs(l - pc))
                trs.append(tr)
            atr = sum(trs) / len(trs) if trs else close * 0.01
    
    if atr <= 0:
        atr = close * 0.01  # Default 1% ATR if unavailable
    
    # Determine direction - ANY trend alignment gives signal
    direction = None
    reason = ""
    
    # Check multiple trend sources
    trend_ema = ind.get('trend_ema', 0)
    trend_sma = ind.get('trend_sma', 0)
    macd_trend = ind.get('macd_trend', 0)
    ema_trend = ind.get('ema_trend', 0)
    
    # Use ANY available trend signal
    if trend_ema > 0 or trend_sma > 0 or macd_trend > 0 or ema_trend > 0:
        direction = "LONG"
        reason = f"Trend UP: ema={ema_fast:.4f}>{ema_slow:.4f}" if ema_fast > ema_slow else "Trend UP detected"
    elif trend_ema < 0 or trend_sma < 0 or macd_trend < 0 or ema_trend < 0:
        direction = "SHORT"
        reason = f"Trend DOWN: ema={ema_fast:.4f}<{ema_slow:.4f}" if ema_fast < ema_slow else "Trend DOWN detected"
    elif close > sma_20:
        direction = "LONG"
        reason = f"Price above SMA20: {close:.4f}>{sma_20:.4f}"
    elif close < sma_20:
        direction = "SHORT"
        reason = f"Price below SMA20: {close:.4f}<{sma_20:.4f}"
    
    # If still no direction, use candle color
    if not direction:
        if close > open_price:
            direction = "LONG"
            reason = "Green candle (price up)"
        elif close < open_price:
            direction = "SHORT"
            reason = "Red candle (price down)"
    
    # If STILL no direction, create one anyway - last resort
    if not direction:
        direction = "LONG" if close > (sma_20 or close * 0.99) else "SHORT"
        reason = "FORCED signal - no clear direction"
    
    # Calculate stops and targets
    rr = 2.0  # Risk-reward
    
    if direction == "LONG":
        stop_loss = close - (1.5 * atr)
        take_profit = close + (rr * (close - stop_loss))
    else:
        stop_loss = close + (1.5 * atr)
        take_profit = close - (rr * (stop_loss - close))
    
    # Basic confidence based on available indicators
    rsi = ind.get('rsi', 50)
    confidence = 0.50
    
    if rsi and rsi != 50:
        if direction == "LONG" and rsi < 50:
            confidence += 0.05
        elif direction == "SHORT" and rsi > 50:
            confidence += 0.05
    
    # Adjust confidence based on EMA alignment
    if ema_fast > 0 and ema_slow > 0:
        if direction == "LONG" and ema_fast > ema_slow:
            confidence += 0.10
        elif direction == "SHORT" and ema_fast < ema_slow:
            confidence += 0.10
    
    confidence = min(0.85, max(0.45, confidence))
    
    signal = {
        'asset': asset,
        'symbol': asset,
        'timeframe': timeframe or '1h',
        'direction': direction,
        'entry': close,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'targets': [take_profit],
        'confidence': confidence,
        'strength': confidence,
        'rr_ratio': rr,
        'strategy_name': 'Emergency Signal',
        'strategy_group': 'emergency',
        'reasoning': f"EMERGENCY: {reason}. ATR-based risks. Force signal to prevent starvation.",
        'atr': atr,
        'is_emergency': True,
        'created_at': datetime.utcnow().isoformat(),
    }
    
    signals.append(signal)
    logger.info(f"[emergency] Generated EMERGENCY signal for {asset}: {direction} @ {close:.4f} conf={confidence:.2f}")
    
    return signals


def diagnose_strategy_failure(asset, market_data):
    """
    Diagnostic function to report WHY strategies aren't generating signals.
    Call this when no signals are found to help debug.
    """
    issues = []
    
    if not market_data:
        issues.append("No market_data at all")
        return issues
    
    # Check each timeframe
    for tf, data in market_data.items():
        if not isinstance(data, dict):
            issues.append(f"{tf}: Not a dict")
            continue
        
        candles = data.get('candles', [])
        if not candles:
            issues.append(f"{tf}: No candles")
            continue
        
        if len(candles) < 20:
            issues.append(f"{tf}: Only {len(candles)} candles (< 20)")
        
        ind = data.get('indicators', {})
        if not ind:
            issues.append(f"{tf}: No indicators")
            continue
        
        # Check key indicator presence
        close = candles[-1].get('close') if candles else None
        sma_20 = ind.get('sma_20')
        ema_20 = ind.get('ema_20')
        ema_fast = ind.get('ema_fast')
        ema_slow = ind.get('ema_slow')
        
        if not close or float(close) <= 0:
            issues.append(f"{tf}: Invalid close price")
        
        if not sma_20 and not ema_20:
            issues.append(f"{tf}: No SMA/SMA average available")
        
        if not ema_fast or not ema_slow:
            issues.append(f"{tf}: No EMA fast/slow for trend")
    
    return issues


# Make it globally available
def get_emergency_signals(asset, market_data, regime=None):
    """Wrapper for backwards compatibility"""
    return force_emergency_signals(asset, market_data, regime)
