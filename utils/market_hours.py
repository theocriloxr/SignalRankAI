"""Market Hours and Broker Mapping Utilities for SignalRankAI.

This module handles:
- Broker mapping for different asset types
- Market hour checks to prevent querying closed markets
- Prevents 429 rate limit errors from querying closed exchanges

Supported Brokers:
- Crypto: BINANCE, BYBIT, COINBASE, KRAKEN (24/7)
- FX: OANDA, FXCM, TVC (Forex.com)
- Equities: NASDAQ, NYSE (US exchanges)
"""

from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)

# Broker mapping for different exchanges
BROKER_MAP = {
    "BINANCE": "BINANCE",
    "BYBIT": "BYBIT",
    "COINBASE": "COINBASE",
    "KRAKEN": "KRAKEN",
    "BITSTAMP": "BITSTAMP",
    "OANDA": "OANDA",
    "FXCM": "FXCM",
    "FOREXCOM": "FOREXCOM",
    "TVC": "TVC",
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE"
}

# Pre-defined broker lists for efficient checking
CRYPTO_BROKERS = [BROKER_MAP["BINANCE"], BROKER_MAP["BYBIT"], BROKER_MAP["COINBASE"], BROKER_MAP["KRAKEN"]]
FX_BROKERS = [BROKER_MAP["OANDA"], BROKER_MAP["FXCM"], BROKER_MAP["TVC"], BROKER_MAP["FOREXCOM"]]
EQUITY_BROKERS = [BROKER_MAP["NASDAQ"], BROKER_MAP["NYSE"]]


def resolve_broker(symbol: str) -> str:
    """Resolve the appropriate broker for a given symbol based on its characteristics.
    
    Args:
        symbol: Trading symbol (e.g., BTCUSDT, XAUUSD, EURUSD)
        
    Returns:
        Broker name from BROKER_MAP
    """
    sym = symbol.upper()
    
    # Crypto symbols (USDT, USDC, BUSD endings or common crypto prefixes)
    if any(suffix in sym for suffix in ["USDT", "USDC", "BUSD"]):
        return BROKER_MAP["BINANCE"]
    if any(c in sym for c in ["BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "AVAX", "MATIC"]):
        return BROKER_MAP["BINANCE"]
    
    # Commodities (XAU = Gold, XAG = Silver, WTI/BRENT = Oil)
    if any(c in sym for c in ["XAU", "XAG", "WTI", "BRENT", "OIL", "NATGAS", "NG"]):
        return BROKER_MAP["TVC"]
    
    # Indices (US30, SPX, DJI, NAS100)
    if any(c in sym for c in ["US30", "SPX", "DJI", "NAS100", "US500", "NDX"]):
        return BROKER_MAP["TVC"]
    
    # FOREX pairs (6-char alphabetic or common FX patterns)
    if len(sym) == 6 and sym.isalpha():
        return BROKER_MAP["OANDA"]
    if "JPY" in sym or "EUR" in sym or "USD" in sym or "GBP" in sym:
        return BROKER_MAP["OANDA"]
    
    # Default to NASDAQ for stocks
    return BROKER_MAP["NASDAQ"]


def is_market_open(symbol: str) -> bool:
    """Check if the market for a given symbol is currently open.
    
    This function blocks the engine from querying closed markets,
    preventing 429 rate limit errors.
    
    Args:
        symbol: Trading symbol
        
    Returns:
        True if market is open, False otherwise
    """
    sym = symbol.upper()
    
    # Crypto markets are 24/7
    broker = resolve_broker(sym)
    if broker in CRYPTO_BROKERS:
        return True
    
    # Get current UTC time
    now = datetime.now()
    
    # FX & Commodities: Close Friday 22:00 UTC, Open Sunday 22:00 UTC
    if broker in FX_BROKERS:
        # Saturday - always closed
        if now.weekday() == 5:
            return False
        # Sunday - only open after 22:00
        if now.weekday() == 6 and now.time() < time(22, 0):
            return False
        # Friday - closed after 22:00
        if now.weekday() == 4 and now.time() >= time(22, 0):
            return False
        return True
    
    # Equities (NYSE/NASDAQ): Mon-Fri 13:30 - 20:00 UTC
    if broker in EQUITY_BROKERS:
        # Weekend
        if now.weekday() >= 5:
            return False
        # Market hours: 13:30 - 20:00 UTC
        market_open_time = time(13, 30)
        market_close_time = time(20, 0)
        if market_open_time <= now.time() <= market_close_time:
            return True
        return False
    
    # Unknown broker - assume open to be safe
    return True


def is_market_open_for_timeframe(symbol: str, timeframe: str) -> bool:
    """Check if market is open, considering the timeframe.
    
    Some timeframes (like 1m, 5m) can be queried even when market is closed,
    but larger timeframes (1h, 4h, 1d) require open markets.
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe (e.g., '1m', '1h', '4h', '1d')
        
    Returns:
        True if market data can be fetched for this timeframe
    """
    # Micro timeframes can sometimes be fetched even when market is "closed"
    micro_timeframes = {'1m', '5m', '15m', '30m'}
    
    if timeframe in micro_timeframes:
        return True
    
    # Larger timeframes require open markets
    return is_market_open(symbol)


def get_market_status(symbol: str) -> dict:
    """Get detailed market status for a symbol.
    
    Args:
        symbol: Trading symbol
        
    Returns:
        Dict with keys: is_open, broker, reason
    """
    sym = symbol.upper()
    broker = resolve_broker(sym)
    is_open = is_market_open(sym)
    
    if is_open:
        return {
            "is_open": True,
            "broker": broker,
            "reason": "market_open"
        }
    
    # Determine why market is closed
    now = datetime.now()
    reason = "unknown"
    
    if broker in CRYPTO_BROKERS:
        reason = "crypto_24_7"
    elif now.weekday() == 5:
        reason = "saturday_closed"
    elif now.weekday() == 6 and now.time() < time(22, 0):
        reason = "sunday_not_yet_open"
    elif now.weekday() == 4 and now.time() >= time(22, 0):
        reason = "friday_closed"
    elif broker in EQUITY_BROKERS:
        if now.weekday() >= 5:
            reason = "weekend"
        else:
            reason = "outside_market_hours"
    
    return {
        "is_open": False,
        "broker": broker,
        "reason": reason
    }


# For backwards compatibility
__all__ = [
    "BROKER_MAP",
    "resolve_broker",
    "is_market_open",
    "is_market_open_for_timeframe",
    "get_market_status"
]
