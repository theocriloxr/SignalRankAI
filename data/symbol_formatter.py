"""
Dynamic Symbol Formatter - Provider-specific symbol formatting.

This module handles symbol format conversion between different data providers:
- Binance/Crypto: BTCUSDT, ETHUSDT (uses USDT suffix)
- Yahoo Finance: BTC-USD, ETH-USD (uses -USD format)
- OANDA: BTC_USD (uses underscore)
- AlphaVantage: BTCUSD (plain format)
- Polygon: X:BTCUSD (prefix format)

The key fix is for the "BTC/USDT" -> "BTC-USD" conversion that yfinance requires.
Without this, yfinance silently returns 0 candles because it can't find the symbol.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Known crypto bases for detection
CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", 
    "LINK", "MATIC", "FIL", "APT", "NEAR", "ALGO", "ATOM", "UNI", "LTC",
    "BCH", "ETC", "XLM", "VET", "HBAR", "ALGB", "FTM", "SAND", "MANA",
    "AAVE", "MKR", "COMP", "SNX", "CRV", "SUSHI", "YFI", "BAT", "ENJ", "CHZ",
}

# Known forex majors for detection  
FOREX_BASES = {
    "EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD", "HKD", "SGD", "SEK", "NOK"
}

# Commodity ticker overrides for Yahoo Finance
COMMONDITY_YAHOO_OVERRIDES = {
    "XAUUSD": "GC=F",   # Gold
    "XAGUSD": "SI=F",   # Silver  
    "WTI": "CL=F",     # Crude Oil
    "WTIUSD": "CL=F",
    "CRUDEOIL": "CL=F",
    "NATGAS": "NG=F",  # Natural Gas
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_crypto_symbol(symbol: str) -> str:
    """
    Normalize a crypto symbol to standard format.
    
    Handles:
    - BTC/USDT -> BTCUSDT
    - BTC-USD -> BTCUSDT
    - BTC_USD -> BTCUSDT
    
    Returns the normalized symbol (e.g., BTCUSDT)
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    
    # Remove common separators
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Handle USDC/USDT variants
    if s.endswith("USDC"):
        s = s[:-4] + "USDT"
    elif s.endswith("USD") and not s.endswith("USDT") and len(s) > 4:
        # BTCUSD -> BTCUSDT
        base = s[:-3]
        if base in CRYPTO_BASES:
            s = base + "USDT"
    
    return s


def format_symbol_for_yahoo(symbol: str) -> str:
    """
    Convert symbol to Yahoo Finance format.
    
    Yahoo Finance requires specific formats:
    - Crypto: BTC-USD (NOT BTC/USDT)
    - Forex: EURUSD=X (with =X suffix)
    - Commodities: GC=F, SI=F, CL=F (futures)
    - Stocks: AAPL, MSFT (plain)
    
    Examples:
    - BTCUSDT -> BTC-USD
    - ETHUSDT -> ETH-USD
    - XAUUSD -> GC=F
    - EURUSD -> EURUSD=X
    
    Returns the Yahoo-compatible symbol.
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    
    # First check for explicit overrides (commodities)
    if s in COMMONDITY_YAHOO_OVERRIDES:
        return COMMONDITY_YAHOO_OVERRIDES[s]
    
    # Clean the symbol
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Detect if it's a crypto pair (ends with USDT or USDC)
    if s.endswith("USDT") or s.endswith("USDC"):
        base = s[:-4]
        return f"{base}-USD"
    
    # If it ends with plain USD, check if it's crypto (base is in crypto_bases)
    if s.endswith("USD") and not s.endswith("USDT"):
        base = s[:-3]
        if base in CRYPTO_BASES:
            return f"{base}-USD"
        # Otherwise it's likely a forex pair or commodity
    
    # Check for forex: 6 char pair like EURUSD, GBPJPY
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        base = s[:3]
        quote = s[3:]
        # If both base and quote are currency codes
        if base in FOREX_BASES and quote in FOREX_BASES:
            return f"{s}=X"
        # Could be a stock ticker - return as-is
    
    # Check for commodity codes
    if s in {"XAU", "GOLD"}:
        return "GC=F"
    if s in {"XAG", "SILVER"}:
        return "SI=F"
    if s in {"WTI", "CL", "OIL"}:
        return "CL=F"
    
    # Default: return as-is (works for stocks)
    return s


def format_symbol_for_oanda(symbol: str) -> str:
    """
    Convert symbol to OANDA format.
    
    OANDA uses: BTC_USD (underscore separator)
    
    Examples:
    - BTCUSDT -> BTC_USD
    - BTC-USD -> BTC_USD
    - EURUSD -> EUR_USD
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    
    # Clean separators
    s = s.replace("/", "").replace("-", "")
    
    # Handle USDT suffix
    if s.endswith("USDT"):
        s = s[:-4] + "_USD"
    elif s.endswith("USD") and len(s) > 3:
        s = s[:-3] + "_USD"
    
    return s


def format_symbol_for_polygon(symbol: str, asset_type: str = "stocks") -> str:
    """
    Convert symbol to Polygon.io format.
    
    Polygon uses prefixes:
    - Crypto: X:BTCUSD
    - Forex: C:EURUSD
    - Stocks: AAPL (plain)
    
    Args:
        symbol: Raw symbol
        asset_type: "crypto", "forex", or "stocks"
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    if asset_type == "crypto":
        # Convert USDT to USD
        if s.endswith("USDT"):
            s = s[:-4] + "USD"
        return f"X:{s}"
    elif asset_type == "forex":
        return f"C:{s}"
    else:
        return s


def format_symbol_for_twelvedata(symbol: str) -> str:
    """
    Convert symbol for Twelve Data API.
    
    Twelve Data generally uses plain format but with some quirks.
    Most symbols work as-is.
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    
    # Remove separators for consistency
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    return s


def format_symbol_for_alphavantage(symbol: str) -> str:
    """
    Convert symbol for AlphaVantage.
    
    AlphaVantage uses plain format: BTCUSD, EURGS
    """
    if not symbol:
        return symbol
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    return s


def get_formatted_symbol_for_provider(
    symbol: str, 
    provider: str,
    asset_type: str = "crypto"
) -> str:
    """
    Get provider-specific formatted symbol.
    
    Args:
        symbol: Raw symbol (e.g., BTCUSDT)
        provider: Provider name (yahoo, oanda, polygon, twelvedata, alphavantage)
        asset_type: Asset type (crypto, forex, stock, commodity)
    
    Returns:
        Provider-formatted symbol
    """
    providers = {
        "yahoo": format_symbol_for_yahoo,
        "oanda": format_symbol_for_oanda,
        "polygon": lambda s: format_symbol_for_polygon(s, asset_type),
        "twelvedata": format_symbol_for_twelvedata,
        "alphavantage": format_symbol_for_alphavantage,
    }
    
    formatter = providers.get(provider.lower())
    if formatter:
        return formatter(symbol)
    
    # Default: return as-is
    return symbol
