"""
Fee Manager - Transparent Fee Structures

Manages transparent fee display, performance fees, subscription rates,
and profit-sharing calculations with High Water Mark method.

Usage:
    from engine.fee_manager import FeeManager, calculate_performance_fee
    
    # Calculate performance fee
    fee = calculate_performance_fee(
        account_balance=10000,
        high_water_mark=9500,
        profit=500,
        fee_rate=0.20  # 20% performance fee
    )
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Fee configuration
DEFAULT_PERFORMANCE_FEE_RATE = 0.20  # 20% of profits
DEFAULT_SUBSCRIPTION_TIERS = {
    "free": {
        "monthly_price": 0,
        "max_trades_per_day": 5,
        "max_concurrent": 2,
    },
    "premium": {
        "monthly_price": 29,
        "max_trades_per_day": 25,
        "max_concurrent": 5,
    },
    "vip": {
        "monthly_price": 99,
        "max_trades_per_day": -1,  # Unlimited
        "max_concurrent": 10,
    },
}


@dataclass
class SubscriptionTier:
    """Subscription tier information."""
    tier_id: str
    name: str
    monthly_price: float
    max_trades_per_day: int
    max_concurrent: int
    features: list


class HighWaterMark:
    """
    Tracks High Water Mark (HWM) for performance fee calculation.
    
    The HWM ensures that performance fees are only charged on NEW profits,
    not on recovery from losses.
    """
    
    def __init__(self):
        self._marks: Dict[int, float] = {}  # user_id -> hwm
    
    def get_hwm(self, user_id: int) -> float:
        """Get HWM for a user."""
        return self._marks.get(user_id, 0.0)
    
    def set_hwm(self, user_id: int, value: float) -> None:
        """Set HWM for a user."""
        self._marks[user_id] = value
    
    def update_hwm(self, user_id: int, new_peak: float) -> float:
        """
        Update HWM if new peak exceeds current.
        
        Returns:
            The updated HWM value
        """
        current = self.get_hwm(user_id)
        if new_peak > current:
            self._marks[user_id] = new_peak
            return new_peak
        return current
    
    def calculate_recoverable_loss(self, user_id: int, current_balance: float) -> float:
        """Calculate recoverable loss from HWM."""
        hwm = self.get_hwm(user_id)
        if current_balance < hwm:
            return hwm - current_balance
        return 0.0


class FeeManager:
    """
    Manages all fee calculations and tracking.
    """
    
    def __init__(self):
        self._hwm = HighWaterMark()
        self._subscription_tiers = DEFAULT_SUBSCRIPTION_TIERS
    
    def calculate_performance_fee(
        self,
        account_balance: float,
        high_water_mark: float,
        profit: float,
        fee_rate: float = DEFAULT_PERFORMANCE_FEE_RATE,
    ) -> float:
        """
        Calculate performance fee using HWM method.
        
        Performance fees are only charged on profits ABOVE the HWM.
        
        Args:
            account_balance: Current account balance
            high_water_mark: Previous peak balance (HWM)
            profit: New profit earned
            fee_rate: Performance fee rate (default 20%)
            
        Returns:
            Performance fee amount
        """
        if profit <= 0:
            return 0.0
        
        # Calculate new HWM
        new_peak = max(account_balance, high_water_mark)
        
        # Only charge fees on profits above HWM
        new_profits = new_peak - high_water_mark
        
        if new_profits <= 0:
            return 0.0
        
        return new_profits * fee_rate
    
    def calculate_net_profit_after_fees(
        self,
        account_balance: float,
        high_water_mark: float,
        profit: float,
        fee_rate: float = DEFAULT_PERFORMANCE_FEE_RATE,
    ) -> float:
        """
        Calculate net profit after performance fees.
        
        Args:
            account_balance: Current account balance
            high_water_mark: Previous peak balance (HWM)
            profit: Total profit earned
            fee_rate: Performance fee rate
            
        Returns:
            Net profit after fees
        """
        if profit <= 0:
            return profit
        
        fee = self.calculate_performance_fee(
            account_balance, high_water_mark, profit, fee_rate
        )
        return profit - fee
    
    def get_subscription_tier(self, tier: str) -> Optional[Dict]:
        """Get subscription tier details."""
        return self._subscription_tiers.get(tier.lower())
    
    def format_tier_info(self, tier: str) -> str:
        """Format subscription tier information for display."""
        tier_info = self.get_subscription_tier(tier)
        if not tier_info:
            return "Unknown tier"
        
        name = tier_info.get("monthly_price", 0)
        trades = tier_info.get("max_trades_per_day", 0)
        concurrent = tier_info.get("max_concurrent", 0)
        
        if trades == -1:
            trades = "Unlimited"
        
        return (
            f"📊 <b>{tier.upper()} Tier</b>\n"
            f"Monthly: ${name:.2f}\n"
            f"Max Trades/Day: {trades}\n"
            f"Max Concurrent: {concurrent}"
        )
    
    def calculate_monthly_revenue(
        self,
        subscribers_by_tier: Dict[str, int],
    ) -> float:
        """
        Calculate total monthly revenue from subscriptions.
        
        Args:
            subscribers_by_tier: Dict of {tier_name: count}
            
        Returns:
            Total monthly revenue
        """
        total = 0.0
        for tier, count in subscribers_by_tier.items():
            tier_info = self.get_subscription_tier(tier)
            if tier_info:
                total += tier_info.get("monthly_price", 0) * count
        return total
    
    def format_fee_structure(self) -> str:
        """Format complete fee structure for display."""
        lines = [
            "💰 <b>Fee Structure</b>",
            "",
            "<b>Performance Fees:</b>",
            f"Rate: {DEFAULT_PERFORMANCE_FEE_RATE * 100:.0f}% of profits",
            "Method: High Water Mark",
            "Only charged on new profits above previous peak",
            "",
            "<b>Subscription Tiers:</b>",
        ]
        
        for tier_id, info in self._subscription_tiers.items():
            price = info.get("monthly_price", 0)
            lines.append(
                f"• {tier_id.upper()}: ${price:.2f}/mo"
            )
        
        return "\n".join(lines)


# Default instance
_fee_manager = FeeManager()


def calculate_performance_fee(
    account_balance: float,
    high_water_mark: float,
    profit: float,
    fee_rate: float = DEFAULT_PERFORMANCE_FEE_RATE,
) -> float:
    """Convenience function for fee calculation."""
    return _fee_manager.calculate_performance_fee(
        account_balance, high_water_mark, profit, fee_rate
    )


def get_fee_manager() -> FeeManager:
    """Get the default fee manager instance."""
    return _fee_manager


def format_all_fees() -> str:
    """Format complete fee structure."""
    return _fee_manager.format_fee_structure()
