"""
Exit Management Module
- Trailing stops
- Multi-tier profit targets
- Break-even stops
- Partial exits
- Time-based exits
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class ExitManager:
    """Manages trade exits with multiple strategies."""
    
    def __init__(self):
        self.exit_history = []
    
    def check_stop_loss(
        self,
        entry_price: float,
        current_price: float,
        stop_loss: float,
        direction: int = 1
    ) -> Tuple[bool, str]:
        """Check if stop loss should be triggered."""
        if direction == 1:  # Long
            if current_price <= stop_loss:
                reason = f"Stop loss hit: {current_price:.2f} <= {stop_loss:.2f}"
                return True, reason
        else:  # Short
            if current_price >= stop_loss:
                reason = f"Stop loss hit: {current_price:.2f} >= {stop_loss:.2f}"
                return True, reason
        
        return False, "SL not hit"
    
    def check_take_profit(
        self,
        current_price: float,
        take_profit: float,
        direction: int = 1
    ) -> Tuple[bool, str]:
        """Check if take profit should be triggered."""
        if direction == 1:  # Long
            if current_price >= take_profit:
                reason = f"Take profit hit: {current_price:.2f} >= {take_profit:.2f}"
                return True, reason
        else:  # Short
            if current_price <= take_profit:
                reason = f"Take profit hit: {current_price:.2f} <= {take_profit:.2f}"
                return True, reason
        
        return False, "TP not hit"
    
    def update_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        current_stop_loss: float,
        atr: float,
        direction: int = 1
    ) -> Dict[str, float]:
        """Update trailing stop, locking in profits."""
        if direction == 1:  # Long
            # Only trail if in profit
            if current_price > entry_price:
                new_stop = current_price - (1.5 * atr)
                # Don't move stop below entry
                new_stop = max(new_stop, entry_price)
                # Don't move stop backwards
                new_stop = max(new_stop, current_stop_loss)
                
                return {
                    'stop_loss': new_stop,
                    'moved': new_stop > current_stop_loss,
                    'movement': new_stop - current_stop_loss
                }
        else:  # Short
            if current_price < entry_price:
                new_stop = current_price + (1.5 * atr)
                new_stop = min(new_stop, entry_price)
                new_stop = min(new_stop, current_stop_loss)
                
                return {
                    'stop_loss': new_stop,
                    'moved': new_stop < current_stop_loss,
                    'movement': current_stop_loss - new_stop
                }
        
        return {
            'stop_loss': current_stop_loss,
            'moved': False,
            'movement': 0
        }
    
    def calculate_breakeven_stop(
        self,
        entry_price: float,
        current_price: float,
        risk_distance: float,
        direction: int = 1
    ) -> Optional[float]:
        """Calculate break-even stop (entry + small buffer)."""
        buffer = risk_distance * 0.2  # 20% of risk as buffer
        
        if direction == 1:  # Long
            # Move stop to entry + buffer once we're 2R in profit
            if current_price >= entry_price + (risk_distance * 2):
                return entry_price + buffer
        else:  # Short
            # Move stop to entry - buffer once we're 2R in profit
            if current_price <= entry_price - (risk_distance * 2):
                return entry_price - buffer
        
        return None
    
    def get_partial_exit_target(
        self,
        partial_targets: List[Dict],
        current_price: float,
        direction: int = 1
    ) -> Optional[Dict]:
        """Check if any partial exit target has been reached."""
        for target in partial_targets:
            price = target.get('price')
            executed = target.get('executed', False)
            
            if executed:
                continue
            
            if direction == 1 and current_price >= price:
                return target
            elif direction == -1 and current_price <= price:
                return target
        
        return None
    
    def time_based_exit(
        self,
        entry_time: datetime,
        current_time: datetime,
        max_hold_hours: int = 24
    ) -> Tuple[bool, str]:
        """Exit trade if held too long without reaching TP."""
        hold_time = current_time - entry_time
        max_duration = timedelta(hours=max_hold_hours)
        
        if hold_time > max_duration:
            reason = f"Time-based exit: held for {hold_time.total_seconds()/3600:.1f}h (max {max_hold_hours}h)"
            return True, reason
        
        return False, "Time limit not reached"
    
    def check_invalidation(
        self,
        entry_price: float,
        current_price: float,
        entry_conditions: Dict,
        indicators: Dict,
        direction: int = 1
    ) -> Tuple[bool, str]:
        """Check if entry signal has been invalidated by price action."""
        # Breakout above entry should never return to entry level for longs
        if direction == 1:
            if current_price < entry_price:
                # Price broke below entry
                rsi = indicators.get('rsi', 50)
                if rsi < 40:  # Momentum also turned negative
                    return True, "Signal invalidated: price below entry + negative momentum"
        
        else:  # Short
            if current_price > entry_price:
                # Price broke above entry
                rsi = indicators.get('rsi', 50)
                if rsi > 60:  # Momentum turned positive
                    return True, "Signal invalidated: price above entry + positive momentum"
        
        return False, "Signal still valid"
    
    def calculate_exit_stats(
        self,
        entry_price: float,
        exit_price: float,
        position_size: float,
        direction: int = 1
    ) -> Dict:
        """Calculate P&L and performance metrics for closed trade."""
        price_diff = exit_price - entry_price
        
        if direction == 1:  # Long
            pnl = price_diff * position_size
            pnl_pct = (price_diff / entry_price) * 100
        else:  # Short
            pnl = -price_diff * position_size
            pnl_pct = -(price_diff / entry_price) * 100
        
        return {
            'entry': entry_price,
            'exit': exit_price,
            'size': position_size,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'win': pnl > 0,
            'loss': pnl < 0,
        }
    
    def suggest_exit_signal(
        self,
        entry_price: float,
        current_price: float,
        current_stop: float,
        atr: float,
        indicators: Dict,
        direction: int = 1,
        max_hold_hours: int = 24
    ) -> Dict:
        """Suggest best exit based on multiple factors."""
        suggestions = []
        
        # 1. Risk/Reward perspective
        entry_to_current = abs(current_price - entry_price)
        entry_to_stop = abs(entry_price - current_stop)
        
        if entry_to_stop > 0:
            rr_achieved = entry_to_current / entry_to_stop
            
            if rr_achieved >= 2.0:
                suggestions.append({
                    'reason': 'Achieved 2:1 R:R target',
                    'priority': 'high',
                    'action': 'take_profit'
                })
        
        # 2. Momentum divergence
        rsi = indicators.get('rsi', 50)
        if direction == 1 and current_price > entry_price and rsi > 70:
            suggestions.append({
                'reason': 'Overbought (RSI >70) after profit',
                'priority': 'medium',
                'action': 'partial_exit'
            })
        elif direction == -1 and current_price < entry_price and rsi < 30:
            suggestions.append({
                'reason': 'Oversold (RSI <30) after profit',
                'priority': 'medium',
                'action': 'partial_exit'
            })
        
        # 3. Trend reversal signals
        macd_trend = indicators.get('macd_trend', 0)
        if direction == 1 and macd_trend < 0:
            suggestions.append({
                'reason': 'MACD turned negative',
                'priority': 'medium',
                'action': 'reduce_position'
            })
        elif direction == -1 and macd_trend > 0:
            suggestions.append({
                'reason': 'MACD turned positive',
                'priority': 'medium',
                'action': 'reduce_position'
            })
        
        # 4. Support/Resistance breakout
        regime = indicators.get('regime', 'unknown')
        if regime == 'ranging':
            suggestions.append({
                'reason': 'Market in range, no momentum',
                'priority': 'low',
                'action': 'consider_exit'
            })
        
        return {
            'should_exit': len(suggestions) > 0,
            'suggestions': suggestions,
            'recommended_action': suggestions[0]['action'] if suggestions else None
        }


class PartialExitTracker:
    """Track which partial exit levels have been executed."""
    
    def __init__(self):
        self.executed_levels = {}
    
    def mark_executed(self, trade_id: str, level_label: str):
        """Mark a partial exit as executed."""
        if trade_id not in self.executed_levels:
            self.executed_levels[trade_id] = set()
        self.executed_levels[trade_id].add(level_label)
    
    def is_executed(self, trade_id: str, level_label: str) -> bool:
        """Check if partial exit has been executed."""
        return level_label in self.executed_levels.get(trade_id, set())
    
    def get_pending_levels(self, trade_id: str, all_levels: List[Dict]) -> List[Dict]:
        """Get list of pending (not yet executed) partial exit levels."""
        executed = self.executed_levels.get(trade_id, set())
        return [level for level in all_levels if level['label'] not in executed]
    
    def reset_trade(self, trade_id: str):
        """Clear tracking for closed trade."""
        if trade_id in self.executed_levels:
            del self.executed_levels[trade_id]
