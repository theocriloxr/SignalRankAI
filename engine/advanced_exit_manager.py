"""
Exit Management System - Near-Zero Loss Trading
Manages stop losses, take profits, and exit strategies to minimize losses.

Features:
1. Dynamic SL placement based on volatility and market structure
2. Break-even stops after TP1 hit
3. Trailing stops for momentum continuation
4. Partial exit scaling (33%/50%/100%)
5. Signal invalidation auto-close
6. Time-based exits
7. Override mechanism for manual control
"""

import os
import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ExitStrategy(Enum):
    """Types of exit strategies."""
    STANDARD = "standard"  # SL + TP levels
    BREAK_EVEN = "break_even"  # Move SL to entry after partial TP
    TRAILING = "trailing"  # Trailing stop
    SCALE_OUT = "scale_out"  # Partial exits
    TIME_BASED = "time_based"  # Exit after X candles
    INVALIDATION = "invalidation"  # Exit when signal invalidated


class AdvancedExitManager:
    """Manages exits to protect capital and maximize wins."""
    
    def __init__(self):
        self.active_exits = {}
        self.exit_history = []
        self.trailing_stops = {}
        
        # Configuration
        self.be_activation_pct = 1.0  # Activate break-even after 1% profit
        self.be_trailing_distance = 0.0015  # 0.15% trailing after BE
        self.max_holding_candles = 20  # Auto-exit after 20 candles
    
    def calculate_smart_stops(
        self,
        entry_price: float,
        atr: float,
        direction: str,
        current_price: float,
        recent_low: float,
        recent_high: float,
        support: float,
        resistance: float
    ) -> Dict:
        """
        Calculate smart stops based on market structure.
        
        For Long:
        - SL: Below recent low or 2*ATR, whichever is tighter
        - TP1: Entry + 2*ATR (1/3 exit)
        - TP2: Entry + 3*ATR (1/2 exit)
        - TP3: Entry + 5*ATR (final exit)
        
        For Short: Opposite
        """
        # Ensure ATR is not zero or too small (use 0.5% of entry as minimum)
        min_atr = entry_price * 0.005  # 0.5% minimum
        effective_atr = max(atr, min_atr)
        
        if direction == "long":
            # SL below recent low (market structure)
            sl_by_structure = recent_low - (0.5 * effective_atr)
            sl_by_atr = entry_price - (2 * effective_atr)
            stop_loss = max(sl_by_structure, sl_by_atr)  # Tightest (least loss)
            
            # Multiple TPs for scaling out (based on ATR, NOT resistance)
            tp1 = entry_price + (2 * effective_atr)
            tp2 = entry_price + (3 * effective_atr)
            tp3 = entry_price + (5 * effective_atr)
            
        else:  # Short
            sl_by_structure = recent_high + (0.5 * effective_atr)
            sl_by_atr = entry_price + (2 * effective_atr)
            stop_loss = min(sl_by_structure, sl_by_atr)
            
            tp1 = entry_price - (2 * effective_atr)
            tp2 = entry_price - (3 * effective_atr)
            tp3 = entry_price - (5 * effective_atr)
        
        # Calculate R:R ratios
        risk = abs(entry_price - stop_loss)
        
        return {
            'entry': entry_price,
            'stop_loss': stop_loss,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'risk_distance': risk,
            'rr_tp1': abs(tp1 - entry_price) / risk if risk > 0 else 0,
            'rr_tp2': abs(tp2 - entry_price) / risk if risk > 0 else 0,
            'rr_tp3': abs(tp3 - entry_price) / risk if risk > 0 else 0,
            'strategy': ExitStrategy.SCALE_OUT.value
        }
    
    def update_to_break_even(
        self,
        trade_id: str,
        entry_price: float,
        tp1_hit_price: float,
        atr: float
    ) -> Dict:
        """
        After TP1 hit, move SL to break-even with tight trailing.
        
        New SL: Entry + 0.15% trailing (near break-even + micro profit)
        """
        profit_at_tp1 = abs(tp1_hit_price - entry_price)
        
        new_sl = entry_price + (0.15 * atr) if tp1_hit_price > entry_price else entry_price - (0.15 * atr)
        
        return {
            'trade_id': trade_id,
            'old_sl': entry_price,
            'new_sl': new_sl,
            'strategy': ExitStrategy.BREAK_EVEN.value,
            'protection': 'BE',
            'description': 'SL moved to break-even, micro trailing active'
        }
    
    def initialize_trailing_stop(
        self,
        trade_id: str,
        entry_price: float,
        atr: float,
        direction: str
    ) -> Dict:
        """
        Initialize trailing stop for momentum continuation.
        
        Trailing distance: 1.5*ATR (moves up with price for long, down for short)
        """
        if direction == "long":
            trailing_sl = entry_price - (1.5 * atr)
        else:
            trailing_sl = entry_price + (1.5 * atr)
        
        self.trailing_stops[trade_id] = {
            'entry': entry_price,
            'direction': direction,
            'atr': atr,
            'current_sl': trailing_sl,
            'highest_price': entry_price if direction == "long" else entry_price,
            'started_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }
        
        return {
            'trade_id': trade_id,
            'trailing_sl': trailing_sl,
            'atr_multiple': 1.5,
            'description': 'Trailing stop initialized'
        }
    
    def update_trailing_stop(
        self,
        trade_id: str,
        current_price: float,
        atr: float
    ) -> Tuple[bool, Optional[float]]:
        """
        Update trailing stop based on current price.
        
        Returns: (should_exit, new_stop_loss)
        """
        if trade_id not in self.trailing_stops:
            return False, None
        
        trail = self.trailing_stops[trade_id]
        direction = trail['direction']
        trailing_distance = 1.5 * atr
        
        if direction == "long":
            # Move SL up as price rises
            if current_price > trail['highest_price']:
                trail['highest_price'] = current_price
                trail['current_sl'] = current_price - trailing_distance
                return False, trail['current_sl']
            
            # Exit if price falls below trailing SL
            if current_price < trail['current_sl']:
                return True, trail['current_sl']
        
        else:  # Short
            # Move SL down as price falls
            if current_price < trail['highest_price']:
                trail['highest_price'] = current_price
                trail['current_sl'] = current_price + trailing_distance
                return False, trail['current_sl']
            
            # Exit if price rises above trailing SL
            if current_price > trail['current_sl']:
                return True, trail['current_sl']
        
        return False, trail['current_sl']
    
    def check_time_based_exit(
        self,
        trade_entry_time: datetime,
        current_time: datetime,
        timeframe: str,
        max_candles: int = 20
    ) -> Tuple[bool, str]:
        """
        Exit if signal has been open too long without movement.
        
        Default: 20 candles (respects timeframe)
        """
        tf_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }
        
        minutes_per_candle = tf_minutes.get(timeframe, 60)
        max_minutes = minutes_per_candle * max_candles
        
        time_held = (current_time - trade_entry_time).total_seconds() / 60
        
        if time_held > max_minutes:
            return True, f"Held {int(time_held/60)}h without significant move"
        
        return False, ""
    
    def check_invalidation_exit(
        self,
        signal: Dict,
        current_price: float,
        indicators: Dict
    ) -> Tuple[bool, str]:
        """
        Exit if signal becomes invalidated.
        
        Invalidation rules:
        1. Price crosses invalidation level
        2. HTF bias flips
        3. Trend reversal (EMA crossover)
        """
        direction = signal.get("direction", "long")
        
        # Rule 1: Kill zone
        invalid_level = signal.get("invalid_if_price")
        if invalid_level:
            if direction == "long" and current_price < invalid_level:
                return True, f"Kill zone breached: {current_price:.2f} < {invalid_level:.2f}"
            elif direction == "short" and current_price > invalid_level:
                return True, f"Kill zone breached: {current_price:.2f} > {invalid_level:.2f}"
        
        # Rule 2: HTF bias flip
        htf_bias = indicators.get("htf_bias", {})
        original_bias = signal.get("htf_bias", {})
        
        if htf_bias != original_bias:
            return True, f"HTF bias flipped from {original_bias} to {htf_bias}"
        
        # Rule 3: Trend reversal (EMA crossover)
        ema_20 = indicators.get("ema_20", 0)
        ema_50 = indicators.get("ema_50", 0)
        
        if direction == "long" and ema_20 < ema_50:
            return True, "EMA20 crossed below EMA50 - trend reversed"
        elif direction == "short" and ema_20 > ema_50:
            return True, "EMA20 crossed above EMA50 - trend reversed"
        
        return False, ""
    
    def calculate_partial_exit_targets(
        self,
        position_size: float,
        entry_price: float,
        tp_levels: List[float]
    ) -> List[Dict]:
        """
        Calculate partial exit scale-out plan.
        
        Default: 33% at TP1, 50% at TP2, 100% at TP3
        """
        exits = []
        
        if len(tp_levels) >= 3:
            exits = [
                {
                    'level': tp_levels[0],
                    'size_pct': 33,
                    'size': position_size * 0.33,
                    'label': 'TP1 - 33% exit',
                    'purpose': 'Lock in first profit'
                },
                {
                    'level': tp_levels[1],
                    'size_pct': 50,
                    'size': position_size * 0.50,
                    'label': 'TP2 - 50% exit',
                    'purpose': 'Lock in more profit'
                },
                {
                    'level': tp_levels[2],
                    'size_pct': 100,
                    'size': position_size * 0.17,  # Remaining
                    'label': 'TP3 - 100% exit',
                    'purpose': 'Final exit for max gain'
                }
            ]
        
        return exits
    
    def get_exit_plan_summary(
        self,
        entry: float,
        stops: Dict,
        position_size: float,
        account_equity: float
    ) -> str:
        """Generate human-readable exit plan."""
        risk_amt = abs(entry - stops['stop_loss'])
        risk_pct = (risk_amt / entry) * 100
        
        account_risk = (risk_amt * position_size) / account_equity * 100
        
        tp1_profit = abs(stops['tp1'] - entry)
        tp2_profit = abs(stops['tp2'] - entry)
        tp3_profit = abs(stops['tp3'] - entry)
        
        summary = f"""
EXIT PLAN:
═══════════════════════════════════════════════════════
🛑 Stop Loss: {stops['stop_loss']:.4f} ({risk_pct:.2f}% from entry)
   Account Risk: {account_risk:.2f}%

🎯 Take Profit Levels:
   TP1: {stops['tp1']:.4f} (+{tp1_profit:.4f}, R:R {stops['rr_tp1']:.2f}:1) → Exit 33%
   TP2: {stops['tp2']:.4f} (+{tp2_profit:.4f}, R:R {stops['rr_tp2']:.2f}:1) → Exit 50%
   TP3: {stops['tp3']:.4f} (+{tp3_profit:.4f}, R:R {stops['rr_tp3']:.2f}:1) → Exit 100%

📊 Position: {position_size:.4f} units
═══════════════════════════════════════════════════════
"""
        return summary


# Global exit manager
advanced_exit = AdvancedExitManager()
