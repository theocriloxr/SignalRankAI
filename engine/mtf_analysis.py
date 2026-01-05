"""
Multi-Timeframe Analysis Module
- HTF trend detection
- LTF entry validation
- Avoid signals against HTF bias
- Timeframe confluence
"""

import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """Analyzes multiple timeframes for trend alignment."""
    
    # Timeframe hierarchy (lower to higher)
    TF_HIERARCHY = {
        '1m': 0, '5m': 1, '15m': 2, '30m': 3, '1h': 4,
        '4h': 5, '1d': 6, '1w': 7, '1M': 8
    }
    
    def __init__(self):
        self.htf_bias_cache = {}
    
    def get_htf_bias(
        self,
        symbol: str,
        current_tf: str,
        candles_data: Dict[str, List[Dict]]
    ) -> Dict:
        """
        Get higher timeframe bias for a symbol.
        
        HTF = timeframe 2-3 steps higher than current
        Example: 5m -> HTF is 1h or 4h
        """
        current_level = self.TF_HIERARCHY.get(current_tf, 2)
        
        # Select HTF (2-3 levels higher)
        htf_candidates = [tf for tf, level in self.TF_HIERARCHY.items() 
                         if level >= current_level + 2]
        
        if not htf_candidates:
            return {'bias': 'neutral', 'confidence': 0, 'tf': None}
        
        htf = htf_candidates[0]  # First available HTF
        
        # Get HTF candles
        htf_candles = candles_data.get(htf, [])
        if not htf_candles or len(htf_candles) < 50:
            return {'bias': 'neutral', 'confidence': 0, 'tf': htf}
        
        # Analyze HTF trend
        df = pd.DataFrame(htf_candles)
        
        # EMA 50/200 trend
        ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema_200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
        close = df['close'].iloc[-1]
        
        # Market structure (HH/LL)
        highs = df['high'].iloc[-20:].values
        lows = df['low'].iloc[-20:].values
        
        higher_highs = self._detect_higher_highs(highs)
        lower_lows = self._detect_lower_lows(lows)
        
        # Determine bias
        bias = 'neutral'
        confidence = 0
        
        if close > ema_50 > ema_200 and higher_highs:
            bias = 'bullish'
            confidence = 80
        elif close < ema_50 < ema_200 and lower_lows:
            bias = 'bearish'
            confidence = 80
        elif close > ema_50:
            bias = 'bullish'
            confidence = 50
        elif close < ema_50:
            bias = 'bearish'
            confidence = 50
        
        return {
            'bias': bias,
            'confidence': confidence,
            'tf': htf,
            'ema_50': ema_50,
            'ema_200': ema_200,
            'structure': 'bullish' if higher_highs else 'bearish' if lower_lows else 'neutral'
        }
    
    def validate_against_htf(
        self,
        signal_direction: str,
        htf_bias: Dict
    ) -> Tuple[bool, str]:
        """
        Validate that signal aligns with HTF bias.
        
        Returns: (is_valid, reason)
        """
        if htf_bias['bias'] == 'neutral':
            return True, "HTF neutral - signal allowed"
        
        # Strong HTF bias (confidence > 70)
        if htf_bias['confidence'] > 70:
            if signal_direction == 'long' and htf_bias['bias'] == 'bearish':
                return False, f"Signal LONG but HTF {htf_bias['tf']} is BEARISH (conf {htf_bias['confidence']}%)"
            elif signal_direction == 'short' and htf_bias['bias'] == 'bullish':
                return False, f"Signal SHORT but HTF {htf_bias['tf']} is BULLISH (conf {htf_bias['confidence']}%)"
        
        # Weak HTF bias (allow counter-trend with caution)
        elif htf_bias['confidence'] > 50:
            if signal_direction == 'long' and htf_bias['bias'] == 'bearish':
                return True, f"Weak HTF BEARISH bias (conf {htf_bias['confidence']}%) - allow with caution"
            elif signal_direction == 'short' and htf_bias['bias'] == 'bullish':
                return True, f"Weak HTF BULLISH bias (conf {htf_bias['confidence']}%) - allow with caution"
        
        return True, f"Signal aligns with HTF {htf_bias['bias']} bias"
    
    def get_mtf_confluence(
        self,
        symbol: str,
        candles_data: Dict[str, List[Dict]],
        signal_direction: str
    ) -> Dict:
        """
        Calculate multi-timeframe confluence score.
        
        Checks: HTF, MTF, LTF all aligned in same direction
        """
        timeframes = sorted(candles_data.keys(), 
                          key=lambda x: self.TF_HIERARCHY.get(x, 99))
        
        if len(timeframes) < 3:
            return {'score': 50, 'aligned_tfs': [], 'conflicting_tfs': []}
        
        aligned = []
        conflicting = []
        
        for tf in timeframes:
            candles = candles_data[tf]
            if len(candles) < 50:
                continue
            
            df = pd.DataFrame(candles)
            ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            close = df['close'].iloc[-1]
            
            tf_bias = 'bullish' if close > ema_50 else 'bearish'
            
            if (signal_direction == 'long' and tf_bias == 'bullish') or \
               (signal_direction == 'short' and tf_bias == 'bearish'):
                aligned.append(tf)
            else:
                conflicting.append(tf)
        
        total_tfs = len(aligned) + len(conflicting)
        confluence_score = (len(aligned) / total_tfs * 100) if total_tfs > 0 else 0
        
        return {
            'score': confluence_score,
            'aligned_tfs': aligned,
            'conflicting_tfs': conflicting,
            'total_checked': total_tfs
        }
    
    def _detect_higher_highs(self, highs) -> bool:
        """Detect higher highs pattern."""
        if len(highs) < 3:
            return False
        return highs[-1] > highs[-2] and highs[-2] > highs[-3]
    
    def _detect_lower_lows(self, lows) -> bool:
        """Detect lower lows pattern."""
        if len(lows) < 3:
            return False
        return lows[-1] < lows[-2] and lows[-2] < lows[-3]


def detect_htf_bias_flip(
    symbol: str,
    current_bias: str,
    previous_bias: str,
    candles: List[Dict]
) -> Dict:
    """
    Detect when HTF bias flips (bullish->bearish or vice versa).
    
    This is a high-probability reversal signal.
    """
    if current_bias == previous_bias:
        return {'flipped': False}
    
    if current_bias == 'neutral' or previous_bias == 'neutral':
        return {'flipped': False}
    
    # Bias flipped
    df = pd.DataFrame(candles)
    
    # Confirm with structure break
    if current_bias == 'bearish':
        # Check if recent candle broke structure low
        recent_low = df['low'].iloc[-10:].min()
        previous_low = df['low'].iloc[-30:-10].min()
        structure_break = recent_low < previous_low
    else:
        # Check if recent candle broke structure high
        recent_high = df['high'].iloc[-10:].max()
        previous_high = df['high'].iloc[-30:-10].max()
        structure_break = recent_high > previous_high
    
    return {
        'flipped': True,
        'from': previous_bias,
        'to': current_bias,
        'structure_confirmed': structure_break,
        'confidence': 90 if structure_break else 60
    }
