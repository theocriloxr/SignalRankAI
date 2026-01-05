"""
Risk Management Module
- Fixed % risk per trade (5% by default)
- ATR-based stop loss and take profit
- Dynamic position sizing
- Max active trades limit
- Trade cooldown
- Correlation avoidance
"""

import os
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

# Configuration
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "5.0"))
MAX_ACTIVE_TRADES = int(os.getenv("MAX_ACTIVE_TRADES", "5"))
TRADE_COOLDOWN_MINUTES = int(os.getenv("TRADE_COOLDOWN_MINUTES", "15"))
MAX_LEVERAGE = 5  # For leverage trading
MIN_RR_RATIO = 2.0  # Minimum reward:risk ratio


class RiskManager:
    """Manages position sizing, stops, and risk per trade."""
    
    def __init__(self, account_equity: float):
        self.account_equity = account_equity
        self.risk_per_trade = account_equity * (RISK_PER_TRADE_PCT / 100)
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        atr: float
    ) -> float:
        """
        Calculate position size based on fixed risk per trade.
        
        Position Size = Risk Amount / (Entry - Stop) * Entry Price
        """
        risk_distance = abs(entry_price - stop_loss)
        
        if risk_distance <= 0:
            return 0
        
        position_size = self.risk_per_trade / risk_distance
        return max(0, position_size)
    
    def calculate_atr_stops(
        self,
        current_price: float,
        atr: float,
        direction: int = 1  # 1 for long, -1 for short
    ) -> Dict[str, float]:
        """
        Calculate ATR-based stop loss and take profit levels.
        
        Long:
            SL = Entry - 2*ATR
            TP = Entry + 4*ATR (or 2:1 R:R minimum)
        Short:
            SL = Entry + 2*ATR
            TP = Entry - 4*ATR
        """
        if direction == 1:  # Long
            stop_loss = current_price - (2 * atr)
            take_profit = current_price + (4 * atr)
            rr_ratio = (take_profit - current_price) / (current_price - stop_loss) if (current_price - stop_loss) > 0 else 0
        else:  # Short
            stop_loss = current_price + (2 * atr)
            take_profit = current_price - (4 * atr)
            rr_ratio = (current_price - take_profit) / (stop_loss - current_price) if (stop_loss - current_price) > 0 else 0
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rr_ratio': rr_ratio,
            'risk_distance': abs(current_price - stop_loss),
            'reward_distance': abs(take_profit - current_price),
        }
    
    def validate_rr_ratio(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        min_ratio: float = MIN_RR_RATIO
    ) -> Tuple[bool, float]:
        """Validate that RR ratio meets minimum requirement."""
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        
        if risk <= 0:
            return False, 0
        
        rr_ratio = reward / risk
        is_valid = rr_ratio >= min_ratio
        
        return is_valid, rr_ratio
    
    def can_open_trade(
        self,
        active_trades: int,
        last_trade_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """Check if new trade can be opened based on limits."""
        # Check max active trades
        if active_trades >= MAX_ACTIVE_TRADES:
            return False, f"Max active trades ({MAX_ACTIVE_TRADES}) reached"
        
        # Check cooldown
        if last_trade_time:
            time_since_last = datetime.utcnow() - last_trade_time
            if time_since_last < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                remaining = TRADE_COOLDOWN_MINUTES - int(time_since_last.total_seconds() / 60)
                return False, f"Trade cooldown: {remaining}m remaining"
        
        return True, "OK"
    
    def calculate_dynamic_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss: float,
        volatility_regime: str = "medium",
        correlation_risk: float = 0.5
    ) -> float:
        """
        Calculate position size with volatility and correlation adjustments.
        
        Reduces size in high volatility or high correlation scenarios.
        """
        base_size = self.calculate_position_size(entry_price, stop_loss, atr=0)
        
        # Volatility adjustment
        if volatility_regime == "high":
            base_size *= 0.7  # 30% reduction in high volatility
        elif volatility_regime == "low":
            base_size *= 1.1  # 10% increase in low volatility
        
        # Correlation adjustment
        correlation_multiplier = 1.0 - (correlation_risk * 0.5)
        base_size *= max(0.3, correlation_multiplier)  # Don't reduce below 30%
        
        return max(0, base_size)
    
    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        atr: float,
        direction: int = 1
    ) -> Optional[float]:
        """
        Calculate trailing stop that locks in profits.
        
        Moves stop loss in direction of trade by 1.5*ATR increments.
        """
        if direction == 1:  # Long
            # Only trail if we're in profit
            if current_price <= entry_price:
                return entry_price - (2 * atr)
            
            # Trail stop above entry
            trailing_stop = current_price - (1.5 * atr)
            return max(trailing_stop, entry_price - (2 * atr))
        
        else:  # Short
            if current_price >= entry_price:
                return entry_price + (2 * atr)
            
            trailing_stop = current_price + (1.5 * atr)
            return min(trailing_stop, entry_price + (2 * atr))
    
    def calculate_partial_exit_levels(
        self,
        entry: float,
        take_profit: float,
        direction: int = 1,
        num_levels: int = 3
    ) -> List[Dict[str, float]]:
        """
        Calculate partial exit levels (e.g., take 1/3 profit at each level).
        
        Default: Exit 33% at TP/3, 33% at TP*2/3, 33% at TP
        """
        if direction == 1:  # Long
            tp_distance = take_profit - entry
            levels = []
            for i in range(1, num_levels + 1):
                level_price = entry + (tp_distance * i / num_levels)
                levels.append({
                    'price': level_price,
                    'quantity_pct': 100 / num_levels,  # Percentage of position
                    'label': f'TP{i}'
                })
            return levels
        
        else:  # Short
            tp_distance = entry - take_profit
            levels = []
            for i in range(1, num_levels + 1):
                level_price = entry - (tp_distance * i / num_levels)
                levels.append({
                    'price': level_price,
                    'quantity_pct': 100 / num_levels,
                    'label': f'TP{i}'
                })
            return levels
    
    def get_optimal_entry_price(
        self,
        current_price: float,
        nearest_support: float,
        nearest_resistance: float,
        direction: int = 1
    ) -> float:
        """
        Calculate optimal entry considering support/resistance levels.
        
        Long: Entry at support with retest, or market order
        Short: Entry at resistance with retest, or market order
        """
        tolerance_pct = 1.0  # 1% tolerance zone
        tolerance = current_price * (tolerance_pct / 100)
        
        if direction == 1:  # Long
            # Ideally enter near support
            if abs(current_price - nearest_support) <= tolerance:
                return current_price  # Already at support
            else:
                return current_price  # Market order
        else:  # Short
            # Ideally enter near resistance
            if abs(current_price - nearest_resistance) <= tolerance:
                return current_price
            else:
                return current_price


class CorrelationManager:
    """Manages correlation between open positions."""
    
    def __init__(self):
        self.correlation_matrix = {}
    
    def calculate_pair_correlation(
        self,
        returns1: np.ndarray,
        returns2: np.ndarray
    ) -> float:
        """Calculate correlation between two assets."""
        if len(returns1) < 2 or len(returns2) < 2:
            return 0
        
        try:
            correlation = np.corrcoef(returns1, returns2)[0, 1]
            return float(correlation) if not np.isnan(correlation) else 0
        except:
            return 0
    
    def can_add_correlated_position(
        self,
        new_pair: str,
        existing_pairs: List[str],
        max_correlation: float = 0.7,
        returns_data: Dict[str, np.ndarray] = None
    ) -> Tuple[bool, str]:
        """Check if new pair has too high correlation with existing positions."""
        if not existing_pairs or not returns_data:
            return True, "No correlation check needed"
        
        for existing in existing_pairs:
            if new_pair not in returns_data or existing not in returns_data:
                continue
            
            corr = self.calculate_pair_correlation(
                returns_data[new_pair],
                returns_data[existing]
            )
            
            if abs(corr) > max_correlation:
                return False, f"High correlation with {existing}: {corr:.2f}"
        
        return True, "OK"
