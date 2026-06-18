"""
Market Session Classifier for SignalRankAI

Consolidates market session detection and asset-class specific hours logic.
 Provides session-aware scoring adjustments based on market conditions.

Sessions:
- PRE_MARKET, OPENING_AUCTION, REGULAR_SESSION, LUNCH_LIQUIDITY_DROP,
  POWER_HOUR, AFTER_HOURS, WEEKEND, HOLIDAY, EARLY_CLOSE, ROLLOVER,
  HIGH_IMPACT_NEWS_WINDOW

Asset Classes:
- Crypto (24/7)
- FX (Session-based)
- Stocks (Exchange-specific)
- Commodities (Product-specific)
"""

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


# Session constants
class MarketSession:
    PRE_MARKET = "PRE_MARKET"
    OPENING_AUCTION = "OPENING_AUCTION"
    REGULAR_SESSION = "REGULAR_SESSION"
    LUNCH_LIQUIDITY_DROP = "LUNCH_LIQUIDITY_DROP"
    POWER_HOUR = "POWER_HOUR"
    AFTER_HOURS = "AFTER_HOURS"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"
    EARLY_CLOSE = "EARLY_CLOSE"
    ROLLOVER = "ROLLOVER"
    HIGH_IMPACT_NEWS_WINDOW = "HIGH_IMPACT_NEWS_WINDOW"


# FX Session hours (UTC)
FX_SESSIONS = {
    "SYDNEY": (22, 0),    # 22:00 UTC
    "TOKYO": (0, 0),       # 00:00 UTC  
    "LONDON": (8, 0),      # 08:00 UTC
    "NEW_YORK": (13, 0),   # 13:00 UTC
}


# Session scoring bonuses (adjustments to score threshold)
SESSION_BONUSES = {
    "LONDON_NY_OVERLAP": 5,      # Most profitable overlap
    "US_EQUITY_POWER_HOUR": 3,  # 09:45-11:30 & 14:00-15:45 EST
    "AFTER_HOURS": -10,          # Lower quality
    "WEEKEND": -15,             # Weekend - lower liquidity
    "HIGH_IMPACT_NEWS": -20,     # News events - skip
    "LUNCH_DROP": -5,           # Lower liquidity during lunch
}


# Asset class multipliers
ASSET_CLASS_MULTIPLIERS = {
    "crypto": 1.0,
    "fx": 1.1,      # FX slightly more reliable
    "stock": 1.2,    # Stocks need higher threshold
    "commodity": 1.0,
    "index": 1.1,
}


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def get_current_session() -> Tuple[str, str]:
    """Get current market session and overlap if applicable.
    
    Returns:
        (session_name, overlap_name)
    """
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    day = now_utc.weekday()
    
    # Weekend check
    if day >= 5:  # Saturday=5, Sunday=6
        return MarketSession.WEEKEND, ""
    
    # FX Session detection
    if hour >= FX_SESSIONS["SYDNEY"][0]:
        return "SYDNEY", ""
    if hour >= FX_SESSIONS["TOKYO"][0]:
        return "TOKYO", ""
    if hour >= FX_SESSIONS["LONDON"][0] and hour < FX_SESSIONS["NEW_YORK"][0]:
        return "LONDON", ""
    if hour >= FX_SESSIONS["NEW_YORK"][0]:
        return "NEW_YORK", ""
    
    # Check for London/NY overlap (most profitable)
    if 13 <= hour < 17:  # 13:00-17:00 UTC
        return "LONDON", "LONDON_NY_OVERLAP"
    
    return MarketSession.REGULAR_SESSION, ""


def get_session_bonus(session_name: str, overlap: str = "") -> float:
    """Get scoring bonus/adjustment for current session.
    
    Args:
        session_name: Current session name
        overlap: Overlap period if applicable
        
    Returns:
        Score adjustment (positive = bonus, negative = penalty)
    """
    if overlap and SESSION_BONUSES.get(overlap):
        return float(SESSION_BONUSES.get(overlap))
    
    if session_name and SESSION_BONUSES.get(session_name):
        return float(SESSION_BONUSES.get(session_name))
    
    return 0.0


def get_asset_class_threshold(base_threshold: float, asset_class: str) -> float:
    """Get adjusted threshold based on asset class.
    
    Args:
        base_threshold: Base score threshold
        asset_class: Asset class (crypto, fx, stock, commodity, index)
        
    Returns:
        Adjusted threshold for asset class
    """
    multiplier = ASSET_CLASS_MULTIPLIERS.get(
        asset_class.lower() if asset_class else "crypto", 
        1.0
    )
    return base_threshold * multiplier


def get_session_state(asset: str = "") -> Dict[str, Any]:
    """Get comprehensive session state for an asset.
    
    Args:
        asset: Optional asset symbol for asset-class specific logic
        
    Returns:
        SessionState dict with:
        - is_open: bool
        - session: str
        - overlap: str  
        - liquidity: str (HIGH, MEDIUM, LOW)
        - risk_level: str (NORMAL, ELEVATED, HIGH)
    """
    session, overlap = get_current_session()
    bonus = get_session_bonus(session, overlap)
    
    # Determine liquidity level
    if overlap or session == "LONDON":
        liquidity = "HIGH"
    elif session == "NEW_YORK":
        liquidity = "MEDIUM"
    else:
        liquidity = "LOW"
    
    # Determine risk level
    high_risk_sessions = [MarketSession.WEEKEND, MarketSession.HIGH_IMPACT_NEWS_WINDOW]
    elevated_risk_sessions = ["LUNCH_LIQUIDITY_DROP", "AFTER_HOURS"]
    closed_sessions = [MarketSession.WEEKEND, MarketSession.HOLIDAY]
    
    if session in high_risk_sessions:
        risk_level = "HIGH"
    elif session in elevated_risk_sessions:
        risk_level = "ELEVATED"
    else:
        risk_level = "NORMAL"
    
    # Determine if market is open
    is_open = session not in closed_sessions
    
    return {
        "is_open": is_open,
        "session": session,
        "overlap": overlap,
        "liquidity": liquidity,
        "risk_level": risk_level,
        "session_bonus": bonus,
    }


def get_time_based_features() -> Dict[str, Any]:
    """Get time-based features for ML training.
    
    Returns:
        Dict with:
        - session: Current session
        - overlap: Active overlap period
        - day_of_week: 0=Monday to 6=Sunday  
        - hour_of_day: 0-23 UTC
        - is_high_impact_news_window: bool
    """
    now_utc = datetime.now(timezone.utc)
    session, overlap = get_current_session()
    
    return {
        "session": session,
        "overlap": overlap,
        "day_of_week": now_utc.weekday(),
        "hour_of_day": now_utc.hour,
        "is_high_impact_news_window": session == MarketSession.HIGH_IMPACT_NEWS_WINDOW,
    }


# Export session state class
@dataclass
class SessionState:
    is_open: bool = True
    session: str = "REGULAR_SESSION"
    overlap: str = ""
    liquidity: str = "MEDIUM"
    risk_level: str = "NORMAL"
    session_bonus: float = 0.0


# Entry point for quick checks
def is_market_open_for_asset(asset: str) -> Tuple[bool, str]:
    """Quick check if market is open for an asset.
    
    Args:
        asset: Asset symbol
        
    Returns:
        (is_open, reason)
    """
    state = get_session_state(asset)
    if not state["is_open"]:
        return False, f"market_closed:{state['session']}"
    
    if state["risk_level"] == "HIGH":
        return False, f"high_risk:{state['session']}"
    
    return True, "ok"


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test session detection
    session, overlap = get_current_session()
    print(f"Current session: {session}, overlap: {overlap}")
    
    # Test session state
    state = get_session_state()
    print(f"Session state: {state}")
    
    # Test time features
    features = get_time_based_features()
    print(f"Time features: {features}")
