"""
Market Regime Filter (The "Chop" Guard)
Uses ADX (Average Directional Index) to determine if the market is actually trending.
If the market is chopping sideways (ADX < threshold), it suppresses trend signals.

This prevents trend strategy hemorrhage in sideways markets.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MarketRegimeFilter:
    """Filters out signals when market is ranging/non-trending."""
    
    def __init__(self, adx_threshold: float = 25.0):
        """
        Initialize the regime filter.
        
        Args:
            adx_threshold: ADX threshold below which market is considered ranging.
                           Default 25 is standard (ADX > 25 = trending).
        """
        self.adx_threshold = float(os.getenv("REGIME_ADX_THRESHOLD", str(adx_threshold)))
    
    def is_trending(self, adx_value: float) -> bool:
        """
        Determine if market is trending based on ADX value.
        
        Args:
            adx_value: The ADX value to evaluate.
            
        Returns:
            True if trending (ADX >= threshold), False if ranging.
        """
        if adx_value is None:
            # No ADX data - default to trending (fail-open)
            logger.debug("[regime_filter] No ADX data, defaulting to trending")
            return True
            
        if float(adx_value) < self.adx_threshold:
            logger.info(f"[regime_filter] Market is RANGING (ADX: {float(adx_value):.2f} < {self.adx_threshold}). Suppressing trend signals.")
            return False
            
        return True
    
    def should_filter(self, adx_value: Optional[float], strategy_type: str = "trend") -> bool:
        """
        Determine if a signal should be filtered based on regime and strategy type.
        
        Args:
            adx_value: The ADX value from market data.
            strategy_type: The strategy type ('trend', 'range', 'momentum', etc.)
            
        Returns:
            True if signal should be filtered/blocked, False if ok to proceed.
        """
        # Only filter trend strategies in ranging markets
        if strategy_type.lower() in ("trend", "momentum", "breakout"):
            if not self.is_trending(adx_value):
                return True
                
        return False


def calculate_adx_from_candles(candles: list) -> Optional[float]:
    """
    Calculate ADX from OHLCV candle data.
    
    This is a simplified calculation. For production, consider using
    pandas_ta or a dedicated indicator library.
    
    Args:
        candles: List of OHLCV candles with 'high', 'low', 'close' keys.
        
    Returns:
        ADX value or None if calculation fails.
    """
    if not candles or len(candles) < 14:
        return None
        
    try:
        # Simplified ATR-based calculation for ADX approximation
        # In production, use: df.ta.adx(length=14)
        highs = [float(c.get('high', 0)) for c in candles if c.get('high')]
        lows = [float(c.get('low', 0)) for c in candles if c.get('low')]
        closes = [float(c.get('close', 0)) for c in candles if c.get('close')]
        
        if len(highs) < 14 or len(lows) < 14 or len(closes) < 14:
            return None
            
        # Calculate True Range series
        trs = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            
            tr = max(
                high - low,
                abs(high - prev_close) if i > 0 else 0,
                abs(low - prev_close) if i > 0 else 0
            )
            trs.append(tr)
            
            plus_dm_move = high - highs[i - 1] if i > 0 else 0
            minus_dm_move = lows[i - 1] - low if i > 0 else 0
            
            if plus_dm_move > minus_dm_move and plus_dm_move > 0:
                plus_dm.append(plus_dm_move)
            else:
                plus_dm.append(0)
                
            if minus_dm_move > plus_dm_move and minus_dm_move > 0:
                minus_dm.append(minus_dm_move)
            else:
                minus_dm.append(0)
        
        if not trs:
            return None
            
        # Smoothed values (14-period SMA)
        period = 14
        smoothed_tr = sum(trs[-period:]) / period if len(trs) >= period else sum(trs) / len(trs)
        smoothed_plus_dm = sum(plus_dm[-period:]) / period if len(plus_dm) >= period else sum(plus_dm) / len(plus_dm)
        smoothed_minus_dm = sum(minus_dm[-period:]) / period if len(minus_dm) >= period else sum(minus_dm) / len(minus_dm)
        
        if smoothed_tr == 0:
            return None
            
        # Calculate +DI and -DI
        plus_di = 100 * (smoothed_plus_dm / smoothed_tr)
        minus_di = 100 * (smoothed_minus_dm / smoothed_tr)
        
        # Calculate DX
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        
        if di_sum == 0:
            return None
            
        dx = 100 * (di_diff / di_sum)
        
        # ADX is smoothed DX (using same period)
        # For simplicity, return DX as ADX approximation
        return dx
        
    except Exception as e:
        logger.debug(f"[regime_filter] ADX calculation failed: {e}")
        return None


# Default instance for easy import
default_regime_filter = MarketRegimeFilter()


async def check_regime_filter(candles: list, strategy_type: str = "trend") -> tuple[bool, Optional[float]]:
    """
    Async wrapper for regime filtering.
    
    Args:
        candles: OHLCV candle data.
        strategy_type: Type of strategy.
        
    Returns:
        Tuple of (should_proceed, adx_value).
    """
    adx_value = calculate_adx_from_candles(candles)
    should_filter = default_regime_filter.should_filter(adx_value, strategy_type)
    return not should_filter, adx_value
