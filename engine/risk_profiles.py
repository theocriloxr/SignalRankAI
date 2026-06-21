"""
Risk Profiles
Phase 5.2 - User-selectable risk preferences

Users choose: Conservative, Balanced, Aggressive
Risk sizing changes automatically based on profile
"""

import logging
import os
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Risk profile definitions
RISK_PROFILES = {
    'conservative': {
        'name': 'Conservative',
        'description': 'Lower risk, steady growth',
        
        # Position sizing
        'max_risk_per_trade': 0.5,  # 0.5% of account
        'max_correlation_risk': 0.15,  # 15% correlation
        'max_open_trades': 3,
        'max_daily_loss': 1.5,  # 1.5% daily stop
        
        # Signal filters
        'min_score': 70,
        'min_rr_ratio': 2.0,
        'min_confidence': 60,
        
        # Asset restrictions
        'allowed_assets': None,  # All allowed
        'blocked_timeframes': ['1m', '5m'],
        'blocked_regimes': ['VOLATILE'],
    },
    'balanced': {
        'name': 'Balanced',
        'description': 'Moderate risk, balanced growth',
        
        # Position sizing
        'max_risk_per_trade': 1.0,  # 1% of account
        'max_correlation_risk': 0.25,  # 25% correlation
        'max_open_trades': 5,
        'max_daily_loss': 3.0,  # 3% daily stop
        
        # Signal filters
        'min_score': 60,
        'min_rr_ratio': 1.5,
        'min_confidence': 50,
        
        # Asset restrictions
        'allowed_assets': None,
        'blocked_timeframes': ['1m'],
        'blocked_regimes': [],
    },
    'aggressive': {
        'name': 'Aggressive',
        'description': 'Higher risk, higher potential returns',
        
        # Position sizing
        'max_risk_per_trade': 2.0,  # 2% of account
        'max_correlation_risk': 0.40,  # 40% correlation
        'max_open_trades': 8,
        'max_daily_loss': 5.0,  # 5% daily stop
        
        # Signal filters
        'min_score': 50,
        'min_rr_ratio': 1.0,
        'min_confidence': 40,
        
        # Asset restrictions
        'allowed_assets': None,
        'blocked_timeframes': [],
        'blocked_regimes': [],
    },
}


@dataclass
class RiskProfile:
    """Risk profile settings."""
    profile_name: str
    profile_id: str
    
    max_risk_per_trade: float
    max_correlation_risk: float
    max_open_trades: int
    max_daily_loss: float
    
    min_score: int
    min_rr_ratio: float
    min_confidence: int
    
    allowed_assets: Optional[list]
    blocked_timeframes: list
    blocked_regimes: list
    
    description: str = ""


def get_risk_profile(profile: str) -> RiskProfile:
    """Get risk profile by name."""
    profile = profile.lower()
    
    if profile not in RISK_PROFILES:
        profile = 'balanced'  # Default
    
    settings = RISK_PROFILES[profile]
    
    return RiskProfile(
        profile_name=settings['name'],
        profile_id=profile,
        max_risk_per_trade=settings['max_risk_per_trade'],
        max_correlation_risk=settings['max_correlation_risk'],
        max_open_trades=settings['max_open_trades'],
        max_daily_loss=settings['max_daily_loss'],
        min_score=settings['min_score'],
        min_rr_ratio=settings['min_rr_ratio'],
        min_confidence=settings['min_confidence'],
        allowed_assets=settings['allowed_assets'],
        blocked_timeframes=settings['blocked_timeframes'],
        blocked_regimes=settings['blocked_regimes'],
        description=settings['description'],
    )


def calculate_position_size(
    profile: str,
    account_balance: float,
    entry_price: float,
    stop_loss: float,
) -> float:
    """
    Calculate position size based on profile.
    
    Returns: Volume/lots to trade
    """
    risk_profile = get_risk_profile(profile)
    
    risk_amount = account_balance * (risk_profile.max_risk_per_trade / 100)
    
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit <= 0:
        return 0
    
    volume = risk_amount / risk_per_unit
    
    return volume


def filter_signal_by_profile(
    profile: str,
    signal: dict,
) -> tuple[bool, str]:
    """
    Filter signal based on risk profile.
    
    Returns: (allowed, reason)
    """
    risk_profile = get_risk_profile(profile)
    
    # Score check
    score = signal.get('score', 0)
    if score < risk_profile.min_score:
        return False, f"score {score} < min {risk_profile.min_score}"
    
    # RR ratio check
    rr = signal.get('rr_ratio') or signal.get('rr_estimate') or 0
    if float(rr) < risk_profile.min_rr_ratio:
        return False, f"RR {rr} < min {risk_profile.min_rr_ratio}"
    
    # Confidence check
    confidence = signal.get('ml_probability', 0) * 100
    if confidence > 0 and confidence < risk_profile.min_confidence:
        return False, f"confidence {confidence:.0f}% < min {risk_profile.min_confidence}"
    
    # Timeframe check
    timeframe = signal.get('timeframe', '').lower()
    if timeframe in risk_profile.blocked_timeframes:
        return False, f"timeframe {timeframe} blocked"
    
    # Regime check
    regime = signal.get('regime', '').upper()
    if regime in risk_profile.blocked_regimes:
        return False, f"regime {regime} blocked"
    
    return True, "allowed"


def format_profile_options() -> str:
    """Format available risk profiles for selection message."""
    lines = [
        "⚙️ <b>Risk Profile Selection</b>",
        "",
    ]
    
    for profile_id, settings in RISK_PROFILES.items():
        lines.append(
            f"<b>{settings['name']}</b>: {settings['description']}"
        )
        lines.append(
            f"  Risk: {settings['max_risk_per_trade']}% | "
            f"Max Trades: {settings['max_open_trades']} | "
            f"Min Score: {settings['min_score']}"
        )
        lines.append("")
    
    lines.append("Use /risk [profile] to select.")
    
    return "\n".join(lines)


# Profile storage (in production, this would be in Redis or DB)
_user_profiles: Dict[str, str] = {}


def set_user_profile(telegram_user_id: int, profile: str) -> bool:
    """Set user's risk profile."""
    profile = profile.lower()
    
    if profile not in RISK_PROFILES:
        return False
    
    _user_profiles[str(telegram_user_id)] = profile
    return True


def get_user_profile(telegram_user_id: int) -> str:
    """Get user's risk profile."""
    return _user_profiles.get(str(telegram_user_id), 'balanced')


def format_current_profile(telegram_user_id: int) -> str:
    """Format user's current risk profile."""
    profile = get_user_profile(telegram_user_id)
    settings = RISK_PROFILES.get(profile, RISK_PROFILES['balanced'])
    
    return (
        f"⚙️ <b>Your Risk Profile</b>\n\n"
        f"Profile: <b>{settings['name']}</b>\n"
        f"Description: {settings['description']}\n\n"
        f"Max Risk/Trade: {settings['max_risk_per_trade']}%\n"
        f"Max Open Trades: {settings['max_open_trades']}\n"
        f"Min Score: {settings['min_score']}\n"
        f"Min RR: {settings['min_rr_ratio']}\n\n"
        "Use /risk [conservative|balanced|aggressive] to change."
    )
