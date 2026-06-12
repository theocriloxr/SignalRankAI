"""
Dynamic Symbol Formatter for Multi-Provider Data Pipeline.

This module provides provider-aware symbol formatting to fix the "silent failure" issue
where yfinance and other providers fail silently due to ticker symbol format mismatches.

Provider Symbol Requirements:
- Binance: BTCUSDT, ETHUSDT (no separator)
- Yahoo Finance: BTC-USD, ETH-USD (uses hyphen, not USDT)
- CryptoCompare: BTCUSDT (understands Binance format)
- Polygon: X:BTCUSD (requires X: prefix for crypto)
- Twelve Data: BTC/USD (uses forward slash)

Usage:
    from data.symbol_formatter import format_symbol_for_provider
    
    # Convert asset to provider-specific format
    yf_symbol = format_symbol_for_provider("BTCUSDT", "yahoo")
    # Returns: "BTC-USD"
"""

import os
import logging

logger = logging.getLogger(__name__)

# Known crypto bases that should use USDT->USD conversion
CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", 
    "DOT", "LINK", "MATIC", "ARB", "OP", "ATOM", "LTC", "UNI",
    "AVAX", "FIL", "APT", "NEAR", "ALGO", "VET", "ICP", "FTM",
    "SAND", "MANA", "AXS", "AAVE", "MKR", "SNX", "CRV", "LDO"
}

# Common overrides for special symbols
SYMBOL_OVERRIDES = {
    # Commodities
    "XAUUSD": "GC=F",  # Gold
    "XAGUSD": "SI=F",  # Silver
    "WTI": "CL=F",    # Crude Oil
    "WTIUSD": "CL=F",
    "CRUDEOIL": "CL=F",
    "NATGAS": "NG=F",
    # Forex majors/crosses
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
}


class SymbolFormatError(Exception):
    """Raised when symbol cannot be formatted for a provider."""
    pass


def _is_crypto_symbol(symbol: str) -> bool:
    """Check if symbol appears to be a crypto pair (USDT/BUSD/USDC suffix)."""
    s = (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    return s.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH")) or s[:3] in CRYPTO_BASES


def format_symbol_for_provider(symbol: str, provider: str) -> str:
    """
    Convert a raw asset symbol to provider-specific format.
    
    Args:
        symbol: Raw asset symbol (e.g., "BTCUSDT", "ETHUSDT", "EURUSD")
        provider: Target provider name ("binance", "yahoo", "cryptocompare", "polygon", "twelvedata", "oanda")
    
    Returns:
        Provider-formatted symbol string
        
    Raises:
        SymbolFormatError: If symbol cannot be formatted
        
    Examples:
        >>> format_symbol_for_provider("BTCUSDT", "yahoo")
        'BTC-USD'
        >>> format_symbol_for_provider("ETHUSDT", "yahoo")
        'ETH-USD'
        >>> format_symbol_for_provider("BTCUSDT", "binance")
        'BTCUSDT'
    """
    if not symbol:
        return symbol
        
    s = str(symbol).upper().strip()
    provider = (provider or "").lower().strip()
    
    # Remove common separators
    s_clean = s.replace("/", "").replace("-", "").replace("_", "")
    
    # Check for commodity overrides first (universal)
    if s_clean in SYMBOL_OVERRIDES:
        return SYMBOL_OVERRIDES[s_clean]
    
    # Provider-specific formatting
    if provider in ("yahoo", "yfinance"):
        # === YAHOO FINANCE FORMAT ===
        # FX: EURUSD -> EURUSD=X
        # Crypto: BTCUSDT -> BTC-USD (NOT BTCUSDT which fails)
        # Crypto: ETHUSDT -> ETH-USD
        
        # Check if it's a crypto pair
        if s_clean.endswith("USDT") and len(s_clean) > 4:
            base = s_clean[:-4]
            # Only convert known crypto bases to avoid false positives
            if base in CRYPTO_BASES or len(base) <= 5:
                return f"{base}-USD"
        
        # Check for USDC/BUSD pairs
        if s_clean.endswith(("USDC", "BUSD")) and len(s_clean) > 4:
            base = s_clean[:-4]
            if base in CRYPTO_BASES or len(base) <= 5:
                return f"{base}-USD"
        
        # Check for BTC/ETH pairs (e.g., ETHBTC)
        if s_clean.endswith(("BTC", "ETH")) and len(s_clean) > 3:
            quote = s_clean[-3:]
            base = s_clean[:-3]
            if quote == "BTC":
                return f"{base}BTC"
            elif quote == "ETH":
                return f"{base}ETH"
        
        # Check for 6-char forex pairs: EURUSD -> EURUSD=X
        if len(s_clean) == 6 and s_clean[:3].isalpha() and s_clean[3:].isalpha():
            return f"{s_clean}=X"
        
        # Default: return cleaned symbol (might still fail but try)
        return s_clean
    
    elif provider in ("binance", "bybit"):
        # === BINANCE/BYBIT FORMAT ===
        # Always use no separator, USDT suffix
        if s_clean.endswith(("USD", "USDC", "BUSD")) and len(s_clean) > 3:
            base = s_clean[:-3]
            return f"{base}USDT"
        
        if s_clean.endswith("USDT"):
            return s_clean  # Already correct
        
        # For plain crypto like BTC, add USDT
        if s_clean in CRYPTO_BASES:
            return f"{s_clean}USDT"
        
        return s_clean
    
    elif provider in ("cryptocompare", "coingecko"):
        # === CRYPTOCOMPARE/COINGECKO FORMAT ===
        # Uses Binance-style format: BTCUSDT
        if s_clean.endswith("USD") and len(s_clean) > 3:
            base = s_clean[:-3]
            if base in CRYPTO_BASES:
                return f"{base}USDT"
        
        if not s_clean.endswith("USDT"):
            if s_clean in CRYPTO_BASES:
                return f"{s_clean}USDT"
        
        return s_clean
    
    elif provider == "polygon":
        # === POLYGON FORMAT ===
        # Crypto: X:BTCUSD
        # Forex: C:EURUSD
        # Stocks: ticker only, no prefix needed
        
        if _is_crypto_symbol(s_clean):
            # Remove USD suffix and add X: prefix
            if s_clean.endswith("USD") and len(s_clean) > 3:
                base = s_clean[:-3]
                return f"X:{base}USD"
            return f"X:{s_clean}"
        
        # Check for forex
        if len(s_clean) == 6 and s_clean[:3].isalpha() and s_clean[3:].isalpha():
            return f"C:{s_clean}"
        
        return s_clean
    
    elif provider == "twelvedata":
        # === TWELVE DATA FORMAT ===
        # Uses forward slash: BTC/USD
        if s_clean.endswith("USDT") and len(s_clean) > 4:
            base = s_clean[:-4]
            return f"{base}/USD"
        
        if s_clean.endswith("USD") and len(s_clean) > 3:
            base = s_clean[:-3]
            return f"{base}/USD"
        
        # Forex pairs use slash
        if len(s_clean) == 6:
            return f"{s_clean[:3]}/{s_clean[3:]}"
        
        return s_clean
    
    elif provider == "oanda":
        # === OANDA FORMAT ===
        # Uses underscore: EUR_USD
        if len(s_clean) == 6:
            return f"{s_clean[:3]}_{s_clean[3:]}"
        
        if s_clean.endswith("USDT") and len(s_clean) > 4:
            base = s_clean[:-4]
            return f"{base}_USD"
        
        return s_clean
    
    else:
        # Default: return cleaned symbol
        return s_clean


def format_symbol_for_yahoo(symbol: str) -> str:
    """Convenience function - format symbol specifically for Yahoo Finance."""
    return format_symbol_for_provider(symbol, "yahoo")


def format_symbol_for_binance(symbol: str) -> str:
    """Convenience function - format symbol specifically for Binance."""
    return format_symbol_for_provider(symbol, "binance")


def format_symbol_for_cryptocompare(symbol: str) -> str:
    """Convenience function - format symbol specifically for CryptoCompare."""
    return format_symbol_for_provider(symbol, "cryptocompare")


def normalize_crypto_symbol(symbol: str) -> str:
    """
    Normalize crypto symbol to a canonical format (BTCUSDT style).
    
    This is the internal canonical format used throughout the system.
    """
    s = (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    
    # Already in canonical format?
    if s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD"):
        return s
    
    # Convert from USD suffix
    if s.endswith("USD") and len(s) > 3:
        base = s[:-3]
        if base in CRYPTO_BASES:
            return f"{base}USDT"
    
    # Plain crypto base
    if s in CRYPTO_BASES:
        return f"{s}USDT"
    
    return s


def detect_symbol_type(symbol: str) -> str:
    """
    Detect the type of symbol based on its format.
    
    Returns:
        "crypto", "fx", "commodity", or "stock"
    """
    s = (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    
    # Commodity check
    if s in SYMBOL_OVERRIDES:
        val = SYMBOL_OVERRIDES[s]
        if val.endswith("=F"):
            return "commodity"
    
    # Crypto check
    if s.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH")):
        return "crypto"
    
    if s[:3] in CRYPTO_BASES and len(s) <= 6:
        return "crypto"
    
    # FX check (6 chars, both parts are currency codes)
    if len(s) == 6 and s[:3].isalpha() and s[3:].isalpha():
        return "fx"
    
    # Default to stock
    return "stock"
