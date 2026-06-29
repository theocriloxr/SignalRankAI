"""
Dynamic Symbol Assignor - Unified provider-specific symbol formatting.

This module provides a single point of entry for all symbol formatting needs,
ensuring each data provider receives the correct symbol format to prevent silent failures.

Key fixes:
1. Yahoo Finance: BTCUSDT -> BTC-USD (NOT BTC/USDT)
2. Minimum 100 candles for 50-period indicators (EMA50, RSI14, etc.)
3. Diagnostic logging to identify exact failure points

Usage:
    from data.dynamic_symbol_assign import get_symbol_for_provider, format_symbol
    
    # Get provider-specific formatted symbol
    yahoo_symbol = get_symbol_for_provider("BTCUSDT", "yahoo")
    # Returns: "BTC-USD"
"""

import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Minimum candles required for technical indicators
# EMA50 needs 50+, RSI14 needs 14+, but we fetch 100+ for margin
MIN_CANDLES_FOR_INDICATORS = 100
MIN_CANDLES_DEGRADED = 50  # Absolute minimum (covers RSI14)

# Known crypto bases for detection
CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", 
    "LINK", "MATIC", "FIL", "APT", "NEAR", "ALGO", "ATOM", "UNI", "LTC",
    "BCH", "ETC", "XLM", "VET", "HBAR", "ALGB", "FTM", "SAND", "MANA",
    "AAVE", "MKR", "COMP", "SNX", "CRV", "SUSHI", "YFI", "BAT", "ENJ", "CHZ",
    "XMR", "TRX", "EOS", "XTZ", "AAVE", "NEO", "KAVA", "COMP", "SUSHI",
}

# Known forex majors for detection  
FOREX_BASES = {
    "EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD", "HKD", "SGD", "SEK", "NOK", "DKK", "PLN"
}

# Commodity ticker overrides for Yahoo Finance
YAHOO_COMMODITY_OVERRIDES = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",  
    "WTI": "CL=F",
    "WTIUSD": "CL=F",
    "CRUDEOIL": "CL=F",
    "NATGAS": "NG=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def detect_asset_type(symbol: str) -> str:
    """
    Detect asset type from symbol.
    
    Returns: 'crypto', 'forex', 'commodity', or 'stock'
    """
    if not symbol:
        return "stock"
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Crypto detection
    if s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD"):
        return "crypto"
    
    if s.endswith("USD") and not s.endswith("USDT") and len(s) > 3:
        base = s[:-3]
        if base in CRYPTO_BASES:
            return "crypto"
    
    # Forex detection (6 char currency pairs)
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        base = s[:3]
        quote = s[3:]
        if base in FOREX_BASES and quote in FOREX_BASES:
            return "forex"
    
    # Commodity detection
    commodity_codes = {"XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER", "WTI", "BRENT", "CL", "NG"}
    for code in commodity_codes:
        if code in s:
            return "commodity"
    
    # Default to stock
    return "stock"


def format_symbol_for_yahoo(symbol: str) -> Tuple[str, str]:
    """
    Convert symbol to Yahoo Finance format with diagnostic info.
    
    Returns: (formatted_symbol, diagnostic_message)
    
    Yahoo Finance requires:
    - Crypto: BTC-USD (NOT BTC/USDT)
    - Forex: EURUSD=X
    - Commodities: GC=F, SI=F, CL=F
    - Stocks: AAPL, MSFT
    """
    if not symbol:
        return symbol, "empty_symbol"
    
    s = str(symbol).upper().strip()
    original = s
    
    # First check for explicit overrides (commodities)
    if s in YAHOO_COMMODITY_OVERRIDES:
        return YAHOO_COMMODITY_OVERRIDES[s], f"commodity_override:{s}"
    
    # Clean the symbol
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Detect if it's a crypto pair
    if s.endswith("USDT") or s.endswith("USDC"):
        base = s[:-4]
        return f"{base}-USD", f"crypto_usdt:{original}->{base}-USD"
    
    # Crypto with plain USD suffix
    if s.endswith("USD") and not s.endswith("USDT") and len(s) > 3:
        base = s[:-3]
        if base in CRYPTO_BASES:
            return f"{base}-USD", f"crypto_usd:{original}->{base}-USD"
    
    # Forex pairs (6 char)
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        base = s[:3]
        quote = s[3:]
        if base in FOREX_BASES and quote in FOREX_BASES:
            return f"{s}=X", f"forex:{original}->{s}=X"
    
    # Commodity check
    if s in {"XAU", "GOLD"}:
        return "GC=F", f"commodity_gold:{original}"
    if s in {"XAG", "SILVER"}:
        return "SI=F", f"commodity_silver:{original}"
    if s in {"WTI", "CL", "OIL"}:
        return "CL=F", f"commodity_oil:{original}"
    
    # Default - return as-is (stocks)
    return s, f"stock:{original}"


def format_symbol_for_oanda(symbol: str) -> Tuple[str, str]:
    """Convert symbol to OANDA format."""
    if not symbol:
        return symbol, "empty"
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "")
    
    if s.endswith("USDT"):
        base = s[:-4]
        return f"{base}_USD", f"crypto:{symbol}->{base}_USD"
    elif s.endswith("USD") and len(s) > 3:
        base = s[:-3]
        return f"{base}_USD", f"crypto_usd:{symbol}->{base}_USD"
    
    # OANDA uses EUR_USD format
    if len(s) == 6:
        base = s[:3]
        quote = s[3:]
        return f"{base}_{quote}", f"forex:{symbol}"
    
    return s, f"default:{symbol}"


def format_symbol_for_polygon(symbol: str, asset_type: str = "stocks") -> Tuple[str, str]:
    """Convert symbol to Polygon.io format."""
    if not symbol:
        return symbol, "empty"
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    if asset_type == "crypto":
        if s.endswith("USDT"):
            s = s[:-4] + "USD"
        return f"X:{s}", f"crypto:{symbol}->X:{s}"
    elif asset_type == "forex":
        return f"C:{s}", f"forex:{symbol}->C:{s}"
    else:
        return s, f"stock:{symbol}"


def format_symbol_for_twelvedata(symbol: str) -> Tuple[str, str]:
    """Convert symbol for Twelve Data API - usually plain format works."""
    if not symbol:
        return symbol, "empty"
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    return s, f"plain:{symbol}"


def format_symbol_for_binance(symbol: str) -> Tuple[str, str]:
    """
    Convert symbol to Binance format.
    
    Binance requires: BTCUSDT (no separators)
    """
    if not symbol:
        return symbol, "empty"
    
    s = str(symbol).upper().strip()
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Ensure USDT suffix
    if s.endswith("USD") and not s.endswith("USDT") and len(s) > 3:
        s = s[:-3] + "USDT"
    
    return s, f"binance:{symbol}->{s}"


def format_symbol_for_cryptocompare(symbol: str) -> Tuple[str, str]:
    """Convert symbol for CryptoCompare API."""
    if not symbol:
        return symbol, "empty"
    
    s = str(symbol).upper().strip()
    # Remove separators
    s = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Extract base if USDT suffix
    if s.endswith("USDT"):
        base = s[:-4]
        return base, f"base_only:{symbol}->{base}"
    elif s.endswith("USD") and len(s) > 3:
        base = s[:-3]
        return base, f"base_only:{symbol}->{base}"
    
    return s, f"default:{symbol}"


def get_symbol_for_provider(
    symbol: str, 
    provider: str,
    asset_type: Optional[str] = None
) -> Tuple[str, str]:
    """
    Get provider-specific formatted symbol with diagnostic info.
    
    Args:
        symbol: Raw symbol (e.g., BTCUSDT, ETHUSDT, EURUSD)
        provider: Provider name (yahoo, oanda, polygon, twelvedata, binance, cryptocompare)
        asset_type: Optional asset type override ('crypto', 'forex', 'commodity', 'stock')
    
    Returns:
        Tuple of (formatted_symbol, diagnostic_message)
    """
    if not symbol:
        return symbol, "empty_symbol"
    
    # Auto-detect asset type if not provided
    if asset_type is None:
        asset_type = detect_asset_type(symbol)
    
    provider = provider.lower().strip()
    
    if provider in ("yahoo", "yfinance", "yahoo_finance"):
        return format_symbol_for_yahoo(symbol)
    elif provider in ("oanda",):
        return format_symbol_for_oanda(symbol)
    elif provider in ("polygon",):
        return format_symbol_for_polygon(symbol, asset_type)
    elif provider in ("twelvedata", "twelvedata"):
        return format_symbol_for_twelvedata(symbol)
    elif provider in ("binance",):
        return format_symbol_for_binance(symbol)
    elif provider in ("cryptocompare",):
        return format_symbol_for_cryptocompare(symbol)
    else:
        # Unknown provider - return as-is
        return symbol, f"unknown_provider:{provider}"


def log_symbol_diagnostic(symbol: str, provider: str, result: Tuple[str, str]) -> None:
    """Log symbol transformation for debugging."""
    formatted, diagnostic = result
    logger.info(f"[symbol_assign] {symbol} -> provider={provider} -> {formatted} ({diagnostic})")


def get_min_candles_required(timeframe: str = "1h") -> int:
    """
    Get minimum candles required for the timeframe.
    
    For indicators like EMA50, RSI14 to work properly, we need at least
    50 candles. To be safe and allow for gaps, we fetch 100+.
    
    Args:
        timeframe: Timeframe string (e.g., '1h', '4h', '1d')
    
    Returns:
        Minimum number of candles to fetch
    """
    # Check environment override
    env_min = os.getenv("MIN_CANDLES_FOR_INDICATORS")
    if env_min:
        try:
            return max(50, int(env_min))
        except Exception:
            pass
    
    # Default based on timeframe
    # 1h: 100 gives us ~4 days of data (enough for EMA50)
    # 4h: 100 gives us ~16 days
    # 1d: 100 gives us ~3 months
    tf = str(timeframe).lower().strip()
    
    if tf in ("1m", "5m", "15m"):
        return 200  # Need more for short timeframes
    elif tf in ("1h", "2h", "3h", "4h"):
        return 100
    elif tf in ("6h", "8h", "12h"):
        return 80
    elif tf in ("1d",):
        return 60
    else:
        return MIN_CANDLES_FOR_INDICATORS


# Legacy compatibility - simple function for symbol formatting
def format_symbol(symbol: str, provider: str = "yahoo") -> str:
    """Simple wrapper for backward compatibility."""
    formatted, _ = get_symbol_for_provider(symbol, provider)
    return formatted
