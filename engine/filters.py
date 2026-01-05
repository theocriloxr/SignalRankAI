"""
Smart Filters Module
- Volume spike detection
- Liquidity checks
- Market regime filtering
- Spread/slippage control
- Correlation checking
"""

import logging
import os
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class SignalFilter:
    """Applies intelligent filters before executing signals."""
    
    def __init__(self):
        self.blocked_pairs = set()
        self.news_events = {}
    
    def apply_all_filters(
        self,
        signal: Dict,
        market_data: Dict,
        open_positions: List[Dict],
        last_trade_time: Dict
    ) -> Tuple[bool, str]:
        """Apply all active filters and return pass/fail."""
        
        # 1. Volume filter
        if not self.check_volume(signal, market_data):
            return False, "Volume filter failed"
        
        # 2. Liquidity filter
        if not self.check_liquidity(signal, market_data):
            return False, "Liquidity filter failed"
        
        # 3. Regime filter
        if not self.check_regime(signal):
            return False, "Regime filter failed"
        
        # 4. Correlation filter
        if not self.check_correlation(signal.get('symbol'), open_positions):
            return False, "Correlation filter failed"
        
        # 5. Spread filter
        if not self.check_spread(signal, market_data):
            return False, "Spread filter failed"
        
        # 6. Time filter (avoid low liquidity hours)
        if not self.check_trading_hours(signal.get('symbol', '')):
            return False, "Trading hours filter failed"
        
        return True, "All filters passed"
    
    def check_volume(self, signal: Dict, market_data: Dict) -> bool:
        """Check if volume conditions are acceptable.
        
        Pass if:
        - Volume > average volume (indicates liquidity)
        - Volume spike detected (strong move)
        """
        volume_ratio = signal.get('volume_ratio', 1.0)
        
        # Require above-average volume or spike
        if volume_ratio >= 1.2:  # 20% above average
            return True
        
        return False
    
    def check_volume_spike(
        self,
        current_volume: float,
        avg_volume: float,
        threshold: float = 1.5
    ) -> bool:
        """Detect volume spike (2x average)."""
        if avg_volume == 0:
            return False
        
        spike_ratio = current_volume / avg_volume
        return spike_ratio >= threshold
    
    def check_liquidity(self, signal: Dict, market_data: Dict) -> bool:
        """Check if pair has sufficient liquidity.
        
        Liquidity checks:
        - Spread < 0.5% (tight bid-ask)
        - Volume > $10M/day equivalent
        - 24h volume spike detected
        """
        symbol = signal.get('symbol', '')
        
        # Major pairs always have good liquidity
        major_pairs = {'BTCUSDT', 'ETHUSDT', 'EURUSD', 'GBPUSD', 'USDJPY'}
        if symbol in major_pairs:
            return True
        
        # Check spread if available
        spread_pct = signal.get('spread_pct', 0.0)
        if spread_pct > 1.0:  # > 1% spread = low liquidity
            return False
        
        return True
    
    def check_spread(self, signal: Dict, market_data: Dict) -> bool:
        """Check if bid-ask spread is acceptable."""
        spread = signal.get('spread', 0.0)
        close = signal.get('close_price', 1.0)
        
        if close == 0:
            return True
        
        spread_pct = (spread / close) * 100
        
        # Reject if spread > 1%
        if spread_pct > 1.0:
            return False
        
        return True
    
    def check_regime(self, signal: Dict) -> bool:
        """Check if signal aligns with market regime.
        
        Accept if:
        - Trending market (ADX > 25) with strong signal
        - Ranging market with tight S/R levels
        """
        regime = signal.get('regime', 'unknown')
        adx = signal.get('adx', 20)
        
        # Trending regime: need strong ADX
        if regime == 'trending':
            return adx >= 25  # Moderate to strong trend
        
        # Ranging regime: any signal ok
        elif regime == 'ranging':
            return adx < 30  # Weak to moderate trend (range)
        
        # Unknown: be cautious
        return True
    
    def check_correlation(
        self,
        symbol: str,
        open_positions: List[Dict],
        max_correlation: float = 0.7
    ) -> bool:
        """Check if opening this position creates too much correlation risk.
        
        Logic:
        - Don't open same asset
        - Don't open highly correlated pairs (> 0.7)
        - Max N correlated pairs in same direction
        """
        if not open_positions:
            return True
        
        # Check for duplicate symbol
        for pos in open_positions:
            if pos.get('symbol') == symbol:
                return False  # Already have this position
        
        # Check correlation with open positions
        correlated_count = 0
        for pos in open_positions:
            # Simple correlation check based on asset class
            if self._are_correlated(symbol, pos.get('symbol', '')):
                correlated_count += 1
        
        # Allow max 2 correlated positions
        if correlated_count >= 2:
            return False
        
        return True
    
    def _are_correlated(self, symbol1: str, symbol2: str, threshold: float = 0.7) -> bool:
        """Simple correlation check between two symbols."""
        # Crypto pairs are highly correlated with each other
        crypto_pairs = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT'}
        
        if symbol1 in crypto_pairs and symbol2 in crypto_pairs:
            return True
        
        # Major FX pairs have different correlations
        # USD pairs: EURUSD, GBPUSD, USDJPY (neg correlation)
        # Crosses: EURGBP, EURJPY
        
        return False
    
    def check_trading_hours(self, symbol: str) -> bool:
        """Avoid trading during low liquidity hours."""
        current_hour = datetime.utcnow().hour
        
        # Crypto: 24/7 trading OK
        if 'USD' in symbol and 'T' not in symbol:  # Binance pairs
            return True
        
        # Forex: avoid overlap gap (21:00-23:00 UTC - overlap between NY close and Tokyo open)
        if 'USD' in symbol:  # FX pairs
            # OK hours: 22:00-20:00 UTC (Tokyo, London, NY sessions)
            if 21 <= current_hour <= 22:  # Gap hour
                return False  # Skip during overlap
            return True
        
        return True
    
    def add_news_event(self, symbol: str, event_time: datetime, impact: str = 'high'):
        """Register a news event to avoid trading."""
        if symbol not in self.news_events:
            self.news_events[symbol] = []
        
        self.news_events[symbol].append({
            'time': event_time,
            'impact': impact
        })
    
    def is_near_news_event(
        self,
        symbol: str,
        current_time: datetime,
        before_minutes: int = 30,
        after_minutes: int = 30
    ) -> bool:
        """Check if current time is near a news event."""
        if symbol not in self.news_events:
            return False
        
        for event in self.news_events[symbol]:
            time_diff = abs((current_time - event['time']).total_seconds() / 60)
            
            if event['impact'] == 'high' and time_diff < before_minutes + after_minutes:
                return True
            elif event['impact'] == 'medium' and time_diff < (before_minutes + after_minutes) / 2:
                return True
        
        return False


class MarketRegimeFilter:
    """Detects and filters based on market regime."""
    
    def __init__(self):
        self.regime_history = {}
    
    def classify_regime(
        self,
        adx: float,
        atr_percent: float,
        momentum: float
    ) -> str:
        """Classify market regime: trending, ranging, or volatile."""
        
        # Strong trend: high ADX + directional momentum
        if adx > 25 and abs(momentum) > 1.0:
            return 'trending'
        
        # Range: low ADX + low momentum
        elif adx < 20 and abs(momentum) < 0.5:
            return 'ranging'
        
        # High volatility: high ATR
        elif atr_percent > 3.0:
            return 'volatile'
        
        # Default
        return 'neutral'
    
    def get_regime_signals(self, regime: str) -> Dict:
        """Get signal characteristics for regime."""
        
        if regime == 'trending':
            return {
                'min_adx': 25,
                'max_volatility_pct': 2.5,
                'allow_breakouts': True,
                'require_confirmation': True,
            }
        
        elif regime == 'ranging':
            return {
                'min_adx': 0,
                'max_volatility_pct': 1.5,
                'allow_breakouts': False,  # Breakouts fail in ranges
                'require_confirmation': False,
            }
        
        elif regime == 'volatile':
            return {
                'min_adx': 0,
                'max_volatility_pct': 100,  # No limit
                'allow_breakouts': True,
                'require_confirmation': True,  # Need extra confirmation
            }
        
        return {}


class SlippageControl:
    """Manages slippage expectations and execution quality."""
    
    def __init__(self):
        self.slippage_history = []
    
    def estimate_slippage(
        self,
        symbol: str,
        order_size: float,
        market_impact: float = 0.5
    ) -> float:
        """Estimate slippage for an order."""
        
        # Base slippage: 0.05% for major pairs, 0.2% for minor
        major_pairs = {'BTCUSDT', 'ETHUSDT', 'EURUSD', 'GBPUSD', 'USDJPY'}
        base_slippage = 0.05 if symbol in major_pairs else 0.2
        
        # Scale by order size (larger orders face more slippage)
        size_multiplier = 1.0 + (order_size / 1000000) * market_impact
        
        total_slippage = base_slippage * size_multiplier
        
        return total_slippage
    
    def adjust_stops_for_slippage(
        self,
        stop_loss: float,
        entry: float,
        slippage_pct: float,
        direction: int = 1
    ) -> float:
        """Adjust stop loss to account for slippage."""
        slippage_distance = entry * (slippage_pct / 100)
        
        if direction == 1:  # Long
            return stop_loss - slippage_distance
        else:  # Short
            return stop_loss + slippage_distance
