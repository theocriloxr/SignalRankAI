"""
Symbol Normalizer - Unified Symbol Resolution

Normalizes symbols from various exchanges/formats into a single canonical form.

Supported formats:
- Crypto: BTCUSD, BTCUSDT, BTC/USD, XBTUSD → BTCUSDT
- Forex: EURUSD, GBPUSD, USDJPY, AUDUSD → Same (standard pair)
- Stocks: AAPL, MSFT, GOOGL → Same (standard ticker)
- Commodities: XAUUSD (Gold), XAGUSD (Silver) → XAUUSD
- Indices: SPX500, NAS100, US30 → Same

Examples:
    normalize("BTCUSD") → "BTCUSDT"
    normalize("BTCUSDT") → "BTCUSDT"
    normalize("BTC/USD") → "BTCUSDT"
    normalize("XBTUSD") → "BTCUSDT"  # Binance legacy
    normalize("EURUSD") → "EURUSD"
    normalize("XAUUSD") → "XAUUSD"
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Pattern, Set

logger = logging.getLogger(__name__)

# Canonical symbol mappings (input → canonical)
_CANONICAL_MAPPINGS: Dict[str, str] = {
    # Crypto Bitcoin variations
    "BTCUSD": "BTCUSDT",
    "BTC/USDT": "BTCUSDT",
    "BTCUSD": "BTCUSDT",
    "XBTUSD": "BTCUSDT",  # Binance legacy
    "XBTUSDT": "BTCUSDT",
    # Crypto Ethereum variations
    "ETHUSD": "ETHUSDT",
    "ETH/USDT": "ETHUSDT",
    "ETHUSD": "ETHUSDT",
    "XETHUSD": "ETHUSDT",
    # Crypto Solana
    "SOLUSD": "SOLUSDT",
    "SOL/USDT": "SOLUSDT",
    # Crypto others (keep USDT suffix)
    "DOGEUSD": "DOGEUSDT",
    "XRPUSD": "XRPUSDT",
    "ADAUSD": "ADAUSDT",
    "DOTUSD": "DOTUSDT",
    "AVAXUSD": "AVAXUSDT",
    "MATICUSD": "MATICUSDT",
    "LINKUSD": "LINKUSDT",
    "ATOMUSD": "ATOMUSDT",
    "UNIUSD": "UNIUSDT",
    "LTCUSD": "LTCUSDT",
    "NEARUSD": "NEARUSDT",
    "APTUSD": "APTUSDT",
    "ARBUSDT": "ARBUSDT",
    "OPUSD": "OPUSDT",
    "INJUSD": "INJUSDT",
    # Commodities
    "XAUUSD": "XAUUSD",  # Gold
    "GOLD": "XAUUSD",
    "XAGUSD": "XAGUSD",  # Silver
    "SILVER": "XAGUSD",
    "CLUSD": "CLFUT",  # Crude Oil
    "NGUSD": "NGFUT",  # Natural Gas
}

# Asset type detection patterns
_ASSET_TYPE_PATTERNS: Dict[str, re.Pattern] = {
    # Crypto (ends with USD or USDT, or is in known crypto list)
    "crypto": re.compile(r"^(BTC|ETH|SOL|XRP|ADA|DOT|AVAX|MATIC|LINK|ATOM|UNI|LTC|NEAR|APT|ARB|OP|INJ|DOGE|XLM|XTZ|MNK|USDT|USD)$", re.IGNORECASE),
    # Forex (major pairs, ends with USD, EUR, JPY, GBP, CHF, CAD, AUD, NZD)
    "forex": re.compile(r"^[A-Z]{3}(USD|EUR|JPY|GBP|CHF|CAD|AUD|NZD)$", re.IGNORECASE),
    # Indices (common patterns)
    "index": re.compile(r"^(SPX|NAS|NDX|US30|US500|WALL|DAX|CAC|FTS|MIB|HNG|NIK|HSI)$", re.IGNORECASE),
    # Commodities
    "commodity": re.compile(r"^(XAU|XAG|GC|SI|CL|NG|F)$", re.IGNORECASE),
}

# Known crypto assets (for ambiguous cases)
_KNOWN_CRYPTO: Set[str] = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "AVAX", "MATIC", "LINK", "ATOM",
    "UNI", "LTC", "NEAR", "APT", "ARB", "OP", "INJ", "DOGE", "XLM", "XTZ",
    "USDT", "USD", "BNB", "FTM", "SAND", "MANA", "AAVE", "MKR", "SNX", "CRV",
}


def _clean_symbol(symbol: str) -> str:
    """Remove spaces, slashes, hyphens and upper-case."""
    if not symbol:
        return ""
    # Remove common separators
    cleaned = re.sub(r"[/ \-]", "", symbol.strip())
    return cleaned.upper()


def _detect_asset_type(symbol: str) -> str:
    """
    Detect the type of asset based on symbol patterns.
    
    Returns: "crypto", "forex", "index", "commodity", "stock", or "unknown"
    """
    sym = _clean_symbol(symbol)
    if not sym:
        return "unknown"
    
    # Check known mappings first
    if sym in _KNOWN_CRYPTO:
        return "crypto"
    
    # Check patterns
    for asset_type, pattern in _ASSET_TYPE_PATTERNS.items():
        if pattern.match(sym):
            return asset_type
    
    # Default unknown
    return "unknown"


def normalize(symbol: str, target_exchange: str = "binance") -> str:
    """
    Normalize a symbol to canonical form.
    
    Args:
        symbol: Input symbol (any format)
        target_exchange: Target exchange (binance, forex, etc.) - currently only binance supported
        
    Returns:
        Canonical symbol string
        
    Examples:
        >>> normalize("BTCUSD")
        'BTCUSDT'
        >>> normalize("BTC/USD")
        'BTCUSDT'
        >>> normalize("EURUSD")
        'EURUSD'
    """
    if not symbol:
        return ""
    
    # Clean the symbol
    cleaned = _clean_symbol(symbol)
    
    # Check direct mapping first
    if cleaned in _CANONICAL_MAPPINGS:
        return _CANONICAL_MAPPINGS[cleaned]
    
    # Handle special cases
    # Crypto without USDT suffix
    if len(cleaned) in {4, 5} and cleaned not in {"USDT", "USDT", "USDC"}:
        # Likely a crypto - add USDT
        if cleaned in _KNOWN_CRYPTO or _detect_asset_type(cleaned) == "crypto":
            return f"{cleaned}USDT"
    
    # Check for forex - keep as is
    if _detect_asset_type(cleaned) == "forex":
        return cleaned
    
    # Default: return cleaned (may be already canonical)
    return cleaned


def normalize_pair(symbol: str, quote_currency: str = "USDT") -> str:
    """
    Normalize a symbol with explicit quote currency.
    
    Args:
        symbol: Base asset symbol
        quote_currency: Quote currency (default: USDT)
        
    Returns:
        Normalized pair symbol
        
    Examples:
        >>> normalize_pair("BTC")
        'BTCUSDT'
        >>> normalize_pair("ETH", "USD")
        'ETHUSD'
    """
    if not symbol:
        return ""
    
    cleaned = _clean_symbol(symbol)
    quote = _clean_symbol(quote_currency) or "USDT"
    
    # Check if already has quote
    if cleaned.endswith(quote):
        return cleaned
    
    # Check mapping
    full = f"{cleaned}{quote}"
    if full in _CANONICAL_MAPPINGS:
        return _CANONICAL_MAPPINGS[full]
    
    return full


def is_crypto(symbol: str) -> bool:
    """Check if symbol is a cryptocurrency."""
    return _detect_asset_type(symbol) == "crypto" or (
        normalize(symbol).endswith("USDT") and len(_clean_symbol(symbol)) > 3
    )


def is_forex(symbol: str) -> bool:
    """Check if symbol is a forex pair."""
    return _detect_asset_type(symbol) == "forex"


def get_base_asset(symbol: str) -> str:
    """Extract base asset from a symbol."""
    normalized = normalize(symbol)
    # Common quotes
    for quote in ["USDT", "USD", "EUR", "GBP", "JPY"]:
        if normalized.endswith(quote):
            return normalized[: -len(quote)]
    return normalized


def get_quote_asset(symbol: str) -> str:
    """Extract quote asset from a symbol."""
    normalized = normalize(symbol)
    # Common quotes
    for quote in ["USDT", "USD", "EUR", "GBP", "JPY"]:
        if normalized.endswith(quote):
            return quote
    return "UNKNOWN"


def batch_normalize(symbols: list[str]) -> dict[str, str]:
    """
    Normalize a batch of symbols.
    
    Args:
        symbols: List of symbols to normalize
        
    Returns:
        Dict mapping original → normalized
        
    Examples:
        >>> batch_normalize(["BTCUSD", "ETH/USD", "EURUSD"])
        {'BTCUSD': 'BTCUSDT', 'ETH/USD': 'ETHUSDT', 'EURUSD': 'EURUSD'}
    """
    return {sym: normalize(sym) for sym in symbols if sym}


# Compatibility alias
resolve_symbol = normalize


__all__ = [
    "normalize",
    "normalize_pair",
    "resolve_symbol",
    "is_crypto",
    "is_forex",
    "get_base_asset",
    "get_quote_asset",
    "batch_normalize",
]
