"""Market hours and holiday calendar for all asset types."""
import math
from datetime import datetime, date, time, timezone
from typing import Optional, Tuple
import logging
import pytz

logger = logging.getLogger(__name__)

# NYSE trading hours (Eastern Time)
NYSE_OPEN = time(9, 30)  # 9:30 AM ET
NYSE_CLOSE = time(16, 0)  # 4:00 PM ET

# CME commodity trading hours (Central Time)
CME_OPEN = time(8, 0)   # 8:00 AM CT (9:00 AM ET)
CME_CLOSE = time(14, 30)  # 2:30 PM CT (3:30 PM ET)


def get_asset_class(asset: str) -> str:
    """Determine asset class from symbol with namespacing support.
    
    Supports:
    - EQUITY:MA -> equity
    - COMMODITY:WTI -> commodity  
    - CRYPTO:BTC -> crypto
    - FORX:EURUSD -> fx
    
    Also supports legacy symbols:
    - BTCUSDT, ETHUSDT -> crypto
    - MA, AAPL -> stock
    - GOLD, SILVER, WTI, XAUUSD -> commodity
    - EURUSD -> fx
    """
    asset_upper = asset.upper()
    
    # Check for namespace prefix
    if ':' in asset:
        prefix = asset_upper.split(':')[0]
        prefix_map = {
            'EQUITY': 'stock',
            'CRYPTO': 'crypto', 
            'COMMODITY': 'commodity',
            'FX': 'fx',
            'FORX': 'fx',
            'FOREX': 'fx',
        }
        if prefix in prefix_map:
            return prefix_map[prefix]
    
    # Crypto detection (USDT, USDC, BUSD suffix or known crypto symbols)
    if asset_upper.endswith(('USDT', 'USDC', 'BUSD', 'BTC', 'ETH')):
        return 'crypto'
    crypto_symbols = {'BTC', 'ETH', 'BNB', 'ADA', 'XRP', 'DOGE', 'SOL', 'DOT', 'MATIC', 'AVAX'}
    if asset_upper in crypto_symbols:
        return 'crypto'
    
    # FX detection (currency pairs)
    if '/' in asset or asset_upper in {'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD'}:
        return 'fx'
    
    # Commodity detection
    commodity_symbols = {'GOLD', 'SILVER', 'OIL', 'XAUUSD', 'XAGUSD', 'WTI', 'BRENT', 'NATGAS'}
    if asset_upper in commodity_symbols:
        return 'commodity'
    
    # Default to stock (single uppercase symbol, 1-5 letters)
    if asset_upper.isalpha() and len(asset_upper) <= 5:
        return 'stock'
    
    return 'stock'  # Default to stock


def is_market_open(asset_class: str) -> Tuple[bool, str]:
    """Check if market is currently open for given asset class.
    
    Args:
        asset_class: One of 'crypto', 'stock', 'commodity', 'fx'
    
    Returns:
        Tuple of (is_open: bool, reason: str)
    """
    # Crypto is always open 24/7
    if asset_class == 'crypto':
        return True, "Crypto markets open 24/7"
    
    # Check holiday first
    holiday_reason = is_stock_holiday()
    if holiday_reason and asset_class in ('stock', 'commodity'):
        return False, holiday_reason
    
    fx_holiday = is_fx_holiday()
    if fx_holiday and asset_class == 'fx':
        return False, fx_holiday
    
    # Get current time in Eastern timezone for market hours check
    # Use UTC hour to determine if DST is active (EDT: March-Nov, else EST)
    now_utc = datetime.now(timezone.utc)
    utc_hour = now_utc.hour
    # Eastern offset: UTC-4 (EDT) or UTC-5 (EST)
    eastern_offset = 4 if (now_utc.month > 3 and now_utc.month < 11) or (now_utc.month == 3 and utc_hour >= 7) or (now_utc.month == 11 and utc_hour < 7) else 5
    eastern_hour = (utc_hour - eastern_offset) % 24
    now_et = now_utc.replace(hour=eastern_hour, minute=now_utc.minute, second=now_utc.second, microsecond=now_utc.microsecond)
    current_time = now_et.time()
    
    # Check if weekday (Monday=0, Sunday=6)
    if now_et.weekday() >= 5:  # Saturday or Sunday
        return False, "Weekend - markets closed"
    
    if asset_class == 'stock':
        # Check NYSE hours
        if current_time < NYSE_OPEN or current_time >= NYSE_CLOSE:
            return False, f"NYSE closed ({NYSE_OPEN.strftime('%H:%M')}-{NYSE_CLOSE.strftime('%H:%M')} ET)"
        return True, f"NYSE open ({current_time.strftime('%H:%M')} ET)"
    
    if asset_class == 'commodity':
        # Check CME hours
        if current_time < CME_OPEN or current_time >= CME_CLOSE:
            return False, f"CME closed ({CME_OPEN.strftime('%H:%M')}-{CME_CLOSE.strftime('%H:%M')} ET)"
        return True, f"CME open ({current_time.strftime('%H:%M')} ET)"
    
    if asset_class == 'fx':
        # FX is more flexible - major pairs trade almost 24/5
        # But reduced liquidity outside major market hours
        if now_et.weekday() >= 5:
            return False, "Weekend - reduced FX liquidity"
        # Major FX sessions: 8:00 ET (London) to 17:00 ET, 8:00 ET to 17:00 ET (New York)
        if current_time < time(8, 0) or current_time >= time(17, 0):
            return False, f"Off-hours - reduced FX liquidity (8:00-17:00 ET)"
        return True, f"FX session active ({current_time.strftime('%H:%M')} ET)"
    
    # Unknown asset class - assume open
    return True, f"Unknown asset class '{asset_class}' - assuming open"

# US Market Holidays (NYSE/NASDAQ) - 2025-2027
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
    # 2027
    date(2027, 1, 1),   # New Year's Day
    date(2027, 1, 18),  # MLK Day
    date(2027, 2, 15),  # Presidents' Day
    date(2027, 3, 26),  # Good Friday
    date(2027, 5, 31),  # Memorial Day
    date(2027, 6, 18),  # Juneteenth (observed)
    date(2027, 7, 5),   # Independence Day (observed)
    date(2027, 9, 6),   # Labor Day
    date(2027, 11, 25), # Thanksgiving
    date(2027, 12, 24), # Christmas (observed)
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
    date(2027, 1, 1),
    date(2027, 12, 24),
    date(2027, 12, 31),
}

def is_fx_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:
    """Return a reason string if FX market is fully closed for a major holiday."""
    now = now_utc or datetime.now(timezone.utc)
    today = now.date()
    if today in FX_REDUCED_LIQUIDITY:
        return f"FX closed (major holiday: {today})"
    return None

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


# Additional Market Session Verification (for engine/core.py)
def is_market_session_open(symbol: str) -> bool:
    """
    Checks if an asset class is eligible for data-fetching or signal evaluation 
    based on asset class specific global market hours.
    
    Args:
        symbol: The asset symbol to check (e.g., "BTCUSDT", "EURUSD", "XAUUSD")
    
    Returns:
        bool: True if market is open for this asset class, False otherwise
    """
    sym = symbol.upper().strip().replace("=X", "")
    now_utc = datetime.now(pytz.utc)
    weekday = now_utc.weekday()  # Monday = 0, Sunday = 6
    current_time = now_utc.time()

    # 1. Crypto Asset Coverage (24/7/365)
    if any(crypto in sym for crypto in ["BTC", "ETH", "SOL", "USDT", "ADA", "AAVE"]):
        return True
        
    # 2. Forex Session Coverage (Sydney, Tokyo, London, New York)
    # Open continuous from Sunday 22:00 UTC to Friday 22:00 UTC
    if len(sym) == 6 or any(fx in sym for fx in ["EUR", "GBP", "USD", "JPY", "AUD", "CAD", "CHF"]):
        if weekday == 5:  # Saturday: Closed
            return False
        if weekday == 6 and current_time < time(22, 0):  # Sunday pre-open: Closed
            return False
        if weekday == 4 and current_time >= time(22, 0):  # Friday post-close: Closed
            return False
        return True

    # 3. Commodities Coverage (XAUUSD, XAGUSD, WTI, BRENT, Natural Gas)
    # Generally open Mon-Fri with a daily 1-hour maintenance break from 21:00 to 22:00 UTC
    if any(comm in sym for comm in ["XAU", "XAG", "WTI", "BRENT", "OIL", "GAS"]):
        if weekday in [5, 6]:  # Weekend closed
            return False
        if time(21, 0) <= current_time < time(22, 0):  # Maintenance window
            return False
        return True

    # 4. Indices Coverage (US30, US500, SPX, DJI, VIX) & Major Stock Markets (NYSE, NASDAQ)
    # Active standard exchange sessions Mon-Fri 14:30 UTC to 21:00 UTC (09:30 AM - 04:00 PM EST)
    if weekday in [5, 6]:
        return False
    market_start = time(14, 30)
    market_end = time(21, 0)
    return market_start <= current_time <= market_end


# =============================================================================
# DATA QUALITY VALIDATION (Fix for generated_signals=0)
# =============================================================================

# Minimum candles required for strategy indicators to work properly
MIN_CANDLES_REQUIRED = 150

# Maximum allowed NaN ratio in close prices
MAX_NAN_RATIO = 0.05

# Timeframe intervals in seconds for staleness calculation
TF_SECONDS = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
    '4h': 14400,
    '1d': 86400,
    '1w': 604800,
}


def validate_data_quality(market_data: dict, asset: str, min_candles: int = MIN_CANDLES_REQUIRED) -> Tuple[bool, str]:
    """
    Validate data quality before strategy execution.
    
    This is the KEY fix for generated_signals=0 - strategies need valid data
    to produce signals. Empty or bad quality data causes signal starvation.
    
    Args:
        market_data: Dict of {timeframe: {candles: [], indicators: {}, ...}}
        asset: Asset symbol for logging
        min_candles: Minimum candles required (default 150)
    
    Returns:
        Tuple of (is_valid: bool, reason: str)
        - reason is empty string if valid, otherwise reason for rejection
    """
    if not market_data:
        return False, "empty_market_data"
    
    # Check at least one timeframe has data
    valid_timeframes = 0
    for tf, tf_data in market_data.items():
        if not isinstance(tf_data, dict):
            continue
            
        candles = tf_data.get('candles', [])
        
        # Check minimum candles (lenient - allow any timeframe with enough data)
        if len(candles) < min_candles:
            logger.debug(f"[data_quality] {asset} {tf}: only {len(candles)} candles (need {min_candles})")
            continue
            
        # Check NaN ratio in close prices
        closes = [c.get('close') for c in candles if c is not None and c.get('close') is not None]
        if not closes:
            logger.debug(f"[data_quality] {asset} {tf}: no close prices")
            continue
            
        nan_count = 0
        for c in closes:
            try:
                if c is None or (isinstance(c, float) and math.isnan(c)):
                    nan_count += 1
            except (TypeError, ValueError):
                try:
                    if float(c) != float(c):  # NaN check
                        nan_count += 1
                except (TypeError, ValueError):
                    pass
        
        nan_ratio = nan_count / len(closes) if closes else 1.0
        if nan_ratio > MAX_NAN_RATIO:
            logger.debug(f"[data_quality] {asset} {tf}: NaN ratio {nan_ratio:.1%} > {MAX_NAN_RATIO:.1%}")
            continue
        
        # Check data freshness (stale data can cause wrong signals)
        data_age = tf_data.get('data_age_seconds', 0)
        tf_interval = TF_SECONDS.get(tf, 3600)
        max_age = tf_interval * 2  # 2x timeframe = allow provider delays
        if data_age > max_age:
            logger.debug(f"[data_quality] {asset} {tf}: data_age {data_age}s > max {max_age}s")
            continue
        
        valid_timeframes += 1
    
    if valid_timeframes == 0:
        return False, f"no_valid_timeframes"
    
    logger.info(f"[data_quality] {asset}: valid data ({valid_timeframes} timeframes)")
    return True, ""


def is_tradeable_now(symbol: str) -> Tuple[bool, str]:
    """
    Check if asset is tradeable NOW with good liquidity.
    
    This filters out assets during poor liquidity sessions:
    - XAUUSD/commodities overnight (20:00-02:00 UTC)
    - Weekend sessions
    
    Args:
        symbol: Asset symbol to check
    
    Returns:
        Tuple of (is_tradeable: bool, reason: str)
    """
    sym = symbol.upper().strip()
    now_utc = datetime.now(pytz.utc)
    hour = now_utc.hour
    
    # Check market session first
    if not is_market_session_open(sym):
        return False, "market_closed"
    
    # Check overnight liquidity (poor for commodities)
    # XAUUSD, XAGUSD (gold/silver) have poor liquidity 20:00-02:00 UTC
    if any(comm in sym for comm in ["XAU", "XAG", "GOLD", "SILVER"]):
        if hour >= 20 or hour < 2:
            return False, "poor_overnight_liquidity"
    
    # WTI, BRENT, OIL have poor overnight liquidity
    if any(comm in sym for comm in ["WTI", "BRENT", "OIL", "NATGAS"]):
        if hour >= 22 or hour < 2:
            return False, "poor_overnight_liquidity"
    
    return True, "tradeable"


def rank_assets_by_priority(assets: list, max_assets: int = 10) -> list:
    """
    Rank assets by analysis priority for Railway/unlimited environments.
    
    Prioritizes:
    1. Assets with active market sessions (not overnight)
    2. Crypto (24/7) during overnight
    3. Major pairs during their active sessions
    
    Args:
        assets: List of asset symbols
        max_assets: Maximum assets to return
    
    Returns:
        List of asset symbols ranked by priority
    """
    ranked = []
    now_utc = datetime.now(pytz.utc)
    hour = now_utc.hour
    
    # During overnight hours (20:00-08:00), prioritize crypto
    is_overnight = hour >= 20 or hour < 8
    
    for asset in assets:
        asset_upper = asset.upper()
        
        # Score based on tradeability
        is_tradeable, reason = is_tradeable_now(asset)
        if not is_tradeable:
            continue
            
        # Boost crypto during overnight
        score = 0
        if is_overnight:
            if 'USDT' in asset_upper or any(c in asset_upper for c in ['BTC', 'ETH', 'SOL']):
                score = 100  # Highest priority for crypto overnight
            else:
                score = 50
        else:
            score = 100  # All assets during regular hours
        
        ranked.append((asset, score))
    
    # Sort by score descending
    ranked.sort(key=lambda x: x[1], reverse=True)
    
    return [a for a, _ in ranked[:max_assets]]
