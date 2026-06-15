"""
Market Hours & Broker Resolution Utility

 Handles broker mappings and strict market hour checks to prevent 
 querying closed markets.

 Issues 7 & 8: Broker Map & Market Hours Support
"""

from datetime import datetime, time
import pytz

# Broker mapping constant
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
    "NYSE": "NYSE",
}


def resolve_broker(symbol: str) -> str:
    """
    Resolve the broker/exchange for a given symbol based on patterns.
    
    Args:
        symbol: The asset symbol to resolve
        
    Returns:
        The broker name from BROKER_MAP
    """
    sym = symbol.upper()
    
    # Crypto:BINANCE
    if any(c in sym for c in ["BTC", "ETH", "SOL", "USDT", "XRP"]):
        return BROKER_MAP["BINANCE"]
    
    # Commodities: TVC
    if any(c in sym for c in ["XAU", "XAG", "WTI", "BRENT", "OIL"]):
        return BROKER_MAP["TVC"]
    
    # Indices: TVC
    if any(c in sym for c in ["US30", "SPX", "DJI", "NAS100"]):
        return BROKER_MAP["TVC"]
    
    # Forex: OANDA (major/minor pairs)
    if len(sym) == 6 or any(c in sym for c in ["JPY", "EUR", "USD", "GBP", "AUD", "CAD", "NZD", "CHF"]):
        return BROKER_MAP["OANDA"]
    
    # Default: NASDAQ for stocks
    return BROKER_MAP["NASDAQ"]


def is_market_open(symbol: str) -> bool:
    """
    Check if the market for a given symbol is currently open.
    
    This function blocks the engine from querying closed markets.
    
    Args:
        symbol: The asset symbol to check
        
    Returns:
        True if market is open, False otherwise
    """
    sym = symbol.upper()
    
    # Get broker for this symbol
    broker = resolve_broker(sym)
    
    # Get current time in UTC
    now = datetime.now(pytz.utc)
    
    # Crypto markets: 24/7
    if broker in ["BINANCE", "BYBIT", "COINBASE"]:
        return True
    
    # Forex & Commodities: Close Friday 22:00 UTC, Open Sunday 22:00 UTC
    if broker in ["OANDA", "FXCM", "TVC"]:
        # Saturday - always closed
        if now.weekday() == 5:
            return False
        # Sunday before 22:00 - closed
        if now.weekday() == 6 and now.time() < time(22, 0):
            return False
        # Friday after 22:00 - closed
        if now.weekday() == 4 and now.time() >= time(22, 0):
            return False
        return True
    
    # Equities (NYSE/NASDAQ): Mon-Fri 13:30 - 20:00 UTC
    if broker in ["NASDAQ", "NYSE"]:
        # Weekend - closed
        if now.weekday() >= 5:
            return False
        # Market hours 13:30 - 20:00 UTC
        if time(13, 30) <= now.time() <= time(20, 0):
            return True
        return False
    
    # Default: assume open
    return True


def get_market_status(symbol: str) -> dict:
    """
    Get detailed market status for a symbol.
    
    Args:
        symbol: The asset symbol to check
        
    Returns:
        Dict with 'is_open', 'broker', 'next_open', 'next_close' keys
    """
    sym = symbol.upper()
    broker = resolve_broker(sym)
    is_open = is_market_open(sym)
    
    now = datetime.now(pytz.utc)
    
    # Calculate next open/close times
    next_open = None
    next_close = None
    
    # For crypto, markets are always open
    if broker in ["BINANCE", "BYBIT", "COINBASE"]:
        return {
            "is_open": True,
            "broker": broker,
            "next_open": "24/7",
            "next_close": "N/A",
        }
    
    # For forex/commodities
    if broker in ["OANDA", "FXCM", "TVC"]:
        if is_open:
            # Find next close (Friday 22:00 UTC)
            if now.weekday() < 4:  # Mon-Thu
                days_ahead = (4 - now.weekday()) % 7
            else:  # Fri
                days_ahead = 0
            if now.weekday() == 4 and now.time() >= time(22, 0):
                days_ahead = 3  # Next Monday
        else:
            # Find next open
            if now.weekday() == 5:  # Saturday
                days_ahead = 2  # Sunday
            elif now.weekday() == 6 and now.time() < time(22, 0):
                days_ahead = 0  # Today (Sunday)
            elif now.weekday() == 4 and now.time() >= time(22, 0):
                days_ahead = 3  # Next Sunday
            else:
                days_ahead = 0
    
    return {
        "is_open": is_open,
        "broker": broker,
        "next_open": next_open,
        "next_close": next_close,
    }


if __name__ == "__main__":
    # Test some symbols
    test_symbols = ["BTCUSDT", "EURUSD", "XAUUSD", "AAPL", "US30"]
    
    print("Market Hours Check:")
    print("-" * 50)
    
    for sym in test_symbols:
        broker = resolve_broker(sym)
        is_open = is_market_open(sym)
        status = "OPEN" if is_open else "CLOSED"
        print(f"{sym}: {broker} - {status}")
