"""
Enhanced signal calculations: profit/loss, risk-reward, position sizing, pips.
"""
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_profit_loss_pct(entry: float, exit_price: float, direction: str) -> float:
    """
    Calculate profit/loss percentage.
    
    Args:
        entry: Entry price
        exit_price: Exit price (TP or current price)
        direction: 'long' or 'short'
    
    Returns:
        Profit/loss as percentage (positive = profit, negative = loss)
    """
    if entry <= 0:
        return 0.0
    
    direction = direction.lower()
    if direction == 'long':
        return ((exit_price - entry) / entry) * 100
    else:  # short
        return ((entry - exit_price) / entry) * 100


def calculate_expected_profit(signal: Dict) -> Optional[float]:
    """Calculate expected profit % based on entry and TP."""
    try:
        entry = float(signal.get('entry', 0))
        direction = signal.get('direction', 'long').lower()
        
        # Get TP - handle both list and single value
        tp_raw = signal.get('take_profit')
        if not tp_raw:
            return None
        
        import json
        if isinstance(tp_raw, str):
            try:
                tp_values = json.loads(tp_raw)
            except:
                tp_values = [float(tp_raw)]
        elif isinstance(tp_raw, list):
            tp_values = tp_raw
        else:
            tp_values = [float(tp_raw)]
        
        if not tp_values:
            return None
        
        tp = float(tp_values[0])
        return calculate_profit_loss_pct(entry, tp, direction)
    
    except Exception as e:
        logger.debug(f"Failed to calculate expected profit: {e}")
        return None


def calculate_expected_loss(signal: Dict) -> Optional[float]:
    """Calculate expected loss % based on entry and SL."""
    try:
        entry = float(signal.get('entry', 0))
        stop_loss = float(signal.get('stop_loss', 0))
        direction = signal.get('direction', 'long').lower()
        
        if stop_loss <= 0:
            return None
        
        return calculate_profit_loss_pct(entry, stop_loss, direction)
    
    except Exception as e:
        logger.debug(f"Failed to calculate expected loss: {e}")
        return None


def calculate_risk_reward(signal: Dict) -> Optional[float]:
    """Calculate risk-reward ratio."""
    try:
        expected_profit = calculate_expected_profit(signal)
        expected_loss = calculate_expected_loss(signal)
        
        if expected_profit is None or expected_loss is None:
            return signal.get('rr_ratio') or signal.get('rr_estimate')
        
        # Ensure loss is positive for RR calculation
        loss_amount = abs(expected_loss)
        if loss_amount <= 0:
            return None
        
        return abs(expected_profit) / loss_amount
    
    except Exception as e:
        logger.debug(f"Failed to calculate RR ratio: {e}")
        return None


def calculate_position_size(signal: Dict, account_balance: float = 10000, risk_pct: float = 1.0) -> Optional[float]:
    """
    Calculate suggested position size using 1% risk rule.
    
    Args:
        signal: Signal dict with entry and stop_loss
        account_balance: Account balance (default 10000)
        risk_pct: Risk percentage per trade (default 1%)
    
    Returns:
        Position size in asset units
    """
    try:
        entry = float(signal.get('entry', 0))
        stop_loss = float(signal.get('stop_loss', 0))
        
        if entry <= 0 or stop_loss <= 0:
            return None
        
        # Calculate risk per unit
        risk_per_unit = abs(entry - stop_loss)
        
        if risk_per_unit <= 0:
            return None
        
        # Total risk amount
        risk_amount = account_balance * (risk_pct / 100)
        
        # Position size
        position_size = risk_amount / risk_per_unit
        
        return position_size
    
    except Exception as e:
        logger.debug(f"Failed to calculate position size: {e}")
        return None


def calculate_pips(asset: str, entry: float, exit_price: float) -> Optional[float]:
    """
    Calculate pip value for FX pairs.
    For most FX pairs: 1 pip = 0.0001
    For JPY pairs: 1 pip = 0.01
    """
    try:
        asset_upper = asset.upper()
        
        # Only calculate for FX pairs
        if '/' not in asset or len(asset) != 7:
            return None
        
        # Determine pip size
        if 'JPY' in asset_upper:
            pip_size = 0.01
        else:
            pip_size = 0.0001
        
        # Calculate pip difference
        price_diff = abs(exit_price - entry)
        pips = price_diff / pip_size
        
        return pips
    
    except Exception as e:
        logger.debug(f"Failed to calculate pips: {e}")
        return None


def calculate_signal_age_minutes(signal: Dict) -> Optional[int]:
    """Calculate signal age in minutes from created_at timestamp."""
    try:
        from datetime import datetime
        
        created_at = signal.get('created_at')
        if not created_at:
            return None
        
        # Handle both datetime objects and string timestamps
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if created_at.tzinfo is not None:
                created_at = created_at.replace(tzinfo=None)
        
        age = datetime.utcnow() - created_at
        return int(age.total_seconds() / 60)
    
    except Exception as e:
        logger.debug(f"Failed to calculate signal age: {e}")
        return None


def get_price_status_indicator(signal: Dict) -> str:
    """
    Get colored indicator for price status.
    
    Returns:
        Emoji indicator showing if conditions are favorable, cautious, or unfavorable
    """
    try:
        current_price = signal.get('current_price')
        entry = float(signal.get('entry', 0))
        direction = signal.get('direction', 'long').lower()
        
        if current_price is None or entry <= 0:
            return "ℹ️"
        
        current_price = float(current_price)
        
        # Calculate drift
        drift_pct = abs(current_price - entry) / entry
        
        # Check if price is moving in favor
        if direction == 'long':
            if current_price < entry * 0.995:  # More than 0.5% below entry
                return "✅"  # Good entry opportunity
            elif current_price > entry * 1.005:  # More than 0.5% above entry
                return "❌"  # Unfavorable entry
            else:
                return "⚠️"  # Near entry
        else:  # short
            if current_price > entry * 1.005:  # More than 0.5% above entry
                return "✅"  # Good entry opportunity
            elif current_price < entry * 0.995:  # More than 0.5% below entry
                return "❌"  # Unfavorable entry
            else:
                return "⚠️"  # Near entry
    
    except Exception as e:
        logger.debug(f"Failed to get price status indicator: {e}")
        return "ℹ️"


def format_enhanced_signal_data(signal: Dict) -> Dict:
    """
    Calculate and format all enhanced signal data.
    
    Returns:
        Dict with calculated fields ready for display
    """
    enhanced = {
        'expected_profit_pct': calculate_expected_profit(signal),
        'expected_loss_pct': calculate_expected_loss(signal),
        'risk_reward_ratio': calculate_risk_reward(signal),
        'suggested_position_size': calculate_position_size(signal),
        'signal_age_minutes': calculate_signal_age_minutes(signal),
        'price_status_indicator': get_price_status_indicator(signal),
    }
    
    # Calculate pips for FX
    asset = signal.get('asset', '')
    entry = signal.get('entry', 0)
    
    # Pips for FX TP
    tp_raw = signal.get('take_profit')
    if tp_raw and entry:
        try:
            import json
            if isinstance(tp_raw, str):
                tp_values = json.loads(tp_raw)
            elif isinstance(tp_raw, list):
                tp_values = tp_raw
            else:
                tp_values = [float(tp_raw)]
            
            if tp_values:
                enhanced['pips_to_tp'] = calculate_pips(asset, float(entry), float(tp_values[0]))
        except:
            pass
    
    # Pips for FX SL
    stop_loss = signal.get('stop_loss', 0)
    if stop_loss and entry:
        enhanced['pips_to_sl'] = calculate_pips(asset, float(entry), float(stop_loss))
    
    return enhanced
