"""
Smart Risk Sizer (ML-Conviction Based Position Sizing)
- Dynamically calculates position size based on ML confidence and SL distance
- High conviction = More risk, Low conviction = Less risk
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("RiskSizer")


class SmartRiskSizer:
    def __init__(
        self,
        account_balance: float = 10000.0,
        base_risk_pct: float = 0.01,
        high_confidence_threshold: float = 0.85,
        medium_confidence_threshold: float = 0.75,
        high_risk_multiplier: float = 1.5,
        medium_risk_multiplier: float = 1.0,
        low_risk_multiplier: float = 0.5,
    ):
        """
        Initialize the Smart Risk Sizer.
        
        Args:
            account_balance: Total account balance in quote currency
            base_risk_pct: Base risk percentage (default 1% = 0.01)
            high_confidence_threshold: ML probability threshold for high conviction (default 0.85)
            medium_confidence_threshold: ML probability threshold for medium conviction (default 0.75)
            high_risk_multiplier: Risk multiplier for high conviction (default 1.5 = 1.5%)
            medium_risk_multiplier: Risk multiplier for medium conviction (default 1.0 = 1.0%)
            low_risk_multiplier: Risk multiplier for low conviction (default 0.5 = 0.5%)
        """
        self.account_balance = account_balance
        self.base_risk_pct = base_risk_pct
        self.high_confidence_threshold = high_confidence_threshold
        self.medium_confidence_threshold = medium_confidence_threshold
        self.high_risk_multiplier = high_risk_multiplier
        self.medium_risk_multiplier = medium_risk_multiplier
        self.low_risk_multiplier = low_risk_multiplier

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        ml_probability: Optional[float] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate exact unit size based on conviction and SL distance.
        
        Args:
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            ml_probability: ML model probability (0-1). If None, uses signal.get('ml_probability')
            signal: Optional signal dict for extracting ml_probability
            
        Returns:
            Position size in units
        """
        # Extract ML probability
        if ml_probability is None:
            if signal is not None:
                ml_probability = signal.get('ml_probability')
            else:
                ml_probability = None
        
        # Determine risk multiplier based on ML probability
        if ml_probability is not None:
            ml_prob = float(ml_probability)
            if ml_prob >= self.high_confidence_threshold:
                risk_multiplier = self.high_risk_multiplier
                conviction_level = "HIGH"
            elif ml_prob >= self.medium_confidence_threshold:
                risk_multiplier = self.medium_risk_multiplier
                conviction_level = "MEDIUM"
            else:
                risk_multiplier = self.low_risk_multiplier
                conviction_level = "LOW"
        else:
            # No ML probability available, use base risk
            risk_multiplier = self.medium_risk_multiplier
            conviction_level = "NONE"

        # Calculate actual risk amount
        actual_risk_amount = self.account_balance * (self.base_risk_pct * risk_multiplier)
        
        # Calculate distance to Stop Loss (absolute)
        sl_distance = abs(float(entry_price) - float(stop_loss))
        
        if sl_distance <= 0:
            logger.warning(
                f"[RiskSizer] Invalid SL distance: entry={entry_price}, sl={stop_loss}. "
                f"Returning 0 position size."
            )
            return 0.0

        # Calculate Position Size: Risk Amount / Stop Loss Distance
        position_size = actual_risk_amount / sl_distance
        
        logger.info(
            f"📐 RISK SIZER: Conviction={conviction_level} "
            f"(ML Prob: {ml_probability*100:.1f}%) -> "
            f"Risk Multiplier: {risk_multiplier}x "
            f"(Risking ${actual_risk_amount:.2f}) -> "
            f"Position Size: {position_size:.4f} units"
        )
        
        return position_size

    def calculate_position_value(
        self,
        entry_price: float,
        stop_loss: float,
        ml_probability: Optional[float] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate position size value in quote currency.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            ml_probability: ML probability
            signal: Optional signal dict
            
        Returns:
            Position value in quote currency
        """
        units = self.calculate_position_size(
            entry_price, stop_loss, ml_probability, signal
        )
        return units * float(entry_price)

    def get_risk_config(self) -> Dict[str, Any]:
        """
        Get current risk configuration.
        
        Returns:
            dict with configuration details
        """
        return {
            'account_balance': self.account_balance,
            'base_risk_pct': self.base_risk_pct,
            'high_confidence_threshold': self.high_confidence_threshold,
            'medium_confidence_threshold': self.medium_confidence_threshold,
            'high_risk_multiplier': self.high_risk_multiplier,
            'medium_risk_multiplier': self.medium_risk_multiplier,
            'low_risk_multiplier': self.low_risk_multiplier,
            'high_risk_pct': self.base_risk_pct * self.high_risk_multiplier,
            'medium_risk_pct': self.base_risk_pct * self.medium_risk_multiplier,
            'low_risk_pct': self.base_risk_pct * self.low_risk_multiplier,
        }

    def update_account_balance(self, new_balance: float) -> None:
        """Update account balance."""
        self.account_balance = float(new_balance)


# Module-level singleton for convenience
_default_sizer: Optional[SmartRiskSizer] = None


def get_risk_sizer(
    account_balance: float = 10000.0,
    base_risk_pct: float = 0.01,
) -> SmartRiskSizer:
    """Get or create the default risk sizer instance."""
    global _default_sizer
    if _default_sizer is None:
        _default_sizer = SmartRiskSizer(
            account_balance=account_balance,
            base_risk_pct=base_risk_pct,
        )
    else:
        # Update balance if provided
        if account_balance != 10000.0:
            _default_sizer.update_account_balance(account_balance)
    return _default_sizer


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    ml_probability: Optional[float] = None,
    account_balance: float = 10000.0,
    base_risk_pct: float = 0.01,
) -> float:
    """
    Convenience function to calculate position size.
    
    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        ml_probability: ML probability (0-1)
        account_balance: Account balance
        base_risk_pct: Base risk percentage
        
    Returns:
        Position size in units
    """
    sizer = get_risk_sizer(account_balance, base_risk_pct)
    return sizer.calculate_position_size(entry_price, stop_loss, ml_probability)
