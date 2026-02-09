"""Market hours and holiday calendar for all asset types."""
from datetime import datetime, date, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# US Market Holidays (NYSE/NASDAQ) - 2025-2026
US_MARKET_HOLIDAYS = {
    # 2025
    date(2025, 1, 1),   # New Year's Day
    date(2025, 1, 20),  # MLK Day
    date(2025, 2, 17),  # Presidents' Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 26),  # Memorial Day
    date(2025, 6, 19),  # Juneteenth
    date(2025, 7, 4),   # Independence Day
    date(2025, 9, 1),   # Labor Day
    date(2025, 11, 27), # Thanksgiving
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

# CME Commodity Holidays (Gold, Silver, Oil)
CME_HOLIDAYS = US_MARKET_HOLIDAYS  # CME follows similar schedule

# FX holidays are minimal - only Christmas and New Year's are universally closed
FX_REDUCED_LIQUIDITY = {
    date(2025, 12, 25),
    date(2025, 12, 31),
    date(2026, 1, 1),
    date(2026, 12, 25),
    date(2026, 12, 31),
}

def is_stock_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:
    """Check if US stock market is closed for a holiday."""
    now = now_utc or datetime.now(timezone.utc)
    today = now.date()
    if today in US_MARKET_HOLIDAYS:
        return f"US stock market closed (holiday: {today})"
    return None

def is_commodity_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:
    """Check if commodity market is closed for a holiday."""
    now = now_utc or datetime.now(timezone.utc)
    today = now.date()
    if today in CME_HOLIDAYS:
        return f"Commodity market closed (CME holiday: {today})"
    return None

def is_fx_low_liquidity(now_utc: Optional[datetime] = None) -> bool:
    """Check if FX market has reduced liquidity due to holidays."""
    now = now_utc or datetime.now(timezone.utc)
    return now.date() in FX_REDUCED_LIQUIDITY
