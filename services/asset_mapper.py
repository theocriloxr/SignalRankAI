"""
services/asset_mapper.py - Unified cross-provider symbol mapping.

Maps a canonical asset name (e.g. "GOLD", "BTCUSDT", "EURUSD") to the
provider-specific symbol format used by each data source.

Usage:
    from services.asset_mapper import map_symbol, classify_asset

    binance_sym  = map_symbol("GOLD", "binance")    # -> "XAUUSDT"
    yfinance_sym = map_symbol("GOLD", "yfinance")   # -> "GC=F"
    polygon_sym  = map_symbol("GOLD", "polygon")    # -> "C:XAUUSD"
    mt5_sym      = map_symbol("GOLD", "mt5")        # -> "XAUUSD"

    asset_class  = classify_asset("BTCUSDT")        # -> "crypto"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core.asset_registry import canonicalize_asset, resolve_asset_spec

# ---------------------------------------------------------------------------
# Canonical symbol overrides per provider
# ---------------------------------------------------------------------------

_CRYPTO_MAP: Dict[str, Dict[str, str]] = {
    # canonical -> {provider: symbol}
    "BTCUSDT": {
        "binance": "BTCUSDT",
        "coingecko": "bitcoin",
        "yfinance": "BTC-USD",
        "polygon": "X:BTCUSD",
        "twelvedata": "BTC/USD",
        "mt5": "BTCUSD",
    },
    "ETHUSDT": {
        "binance": "ETHUSDT",
        "coingecko": "ethereum",
        "yfinance": "ETH-USD",
        "polygon": "X:ETHUSD",
        "twelvedata": "ETH/USD",
        "mt5": "ETHUSD",
    },
    "BNBUSDT": {
        "binance": "BNBUSDT",
        "coingecko": "binancecoin",
        "yfinance": "BNB-USD",
        "polygon": "X:BNBUSD",
        "twelvedata": "BNB/USD",
        "mt5": "BNBUSD",
    },
    "SOLUSDT": {
        "binance": "SOLUSDT",
        "coingecko": "solana",
        "yfinance": "SOL-USD",
        "polygon": "X:SOLUSD",
        "twelvedata": "SOL/USD",
        "mt5": "SOLUSD",
    },
    "XRPUSDT": {
        "binance": "XRPUSDT",
        "coingecko": "ripple",
        "yfinance": "XRP-USD",
        "polygon": "X:XRPUSD",
        "twelvedata": "XRP/USD",
        "mt5": "XRPUSD",
    },
}

_FX_MAP: Dict[str, Dict[str, str]] = {
    "EURUSD": {
        "binance": None,
        "yfinance": "EURUSD=X",
        "polygon": "C:EURUSD",
        "twelvedata": "EUR/USD",
        "alphavantage": "EURUSD",
        "mt5": "EURUSD",
        "oanda": "EUR_USD",
    },
    "GBPUSD": {
        "binance": None,
        "yfinance": "GBPUSD=X",
        "polygon": "C:GBPUSD",
        "twelvedata": "GBP/USD",
        "alphavantage": "GBPUSD",
        "mt5": "GBPUSD",
        "oanda": "GBP_USD",
    },
    "USDJPY": {
        "binance": None,
        "yfinance": "USDJPY=X",
        "polygon": "C:USDJPY",
        "twelvedata": "USD/JPY",
        "alphavantage": "USDJPY",
        "mt5": "USDJPY",
        "oanda": "USD_JPY",
    },
    "USDCHF": {
        "binance": None,
        "yfinance": "USDCHF=X",
        "polygon": "C:USDCHF",
        "twelvedata": "USD/CHF",
        "mt5": "USDCHF",
        "oanda": "USD_CHF",
    },
    "AUDUSD": {
        "binance": None,
        "yfinance": "AUDUSD=X",
        "polygon": "C:AUDUSD",
        "twelvedata": "AUD/USD",
        "mt5": "AUDUSD",
        "oanda": "AUD_USD",
    },
}

_COMMODITY_MAP: Dict[str, Dict[str, str]] = {
    "GOLD": {
        "binance": None,
        "yfinance": "GC=F",
        "polygon": "C:XAUUSD",
        "twelvedata": "XAU/USD",
        "alphavantage": "XAUUSD",
        "mt5": "XAUUSD",
        "oanda": "XAU_USD",
    },
    "XAUUSD": {
        "binance": None,
        "yfinance": "GC=F",
        "polygon": "C:XAUUSD",
        "twelvedata": "XAU/USD",
        "mt5": "XAUUSD",
        "oanda": "XAU_USD",
    },
    "SILVER": {
        "binance": None,
        "yfinance": "SI=F",
        "polygon": "C:XAGUSD",
        "twelvedata": "XAG/USD",
        "mt5": "XAGUSD",
        "oanda": "XAG_USD",
    },
    "XAGUSD": {
        "binance": None,
        "yfinance": "SI=F",
        "polygon": "C:XAGUSD",
        "twelvedata": "XAG/USD",
        "mt5": "XAGUSD",
    },
    "OIL": {
        "binance": None,
        "yfinance": "CL=F",
        "polygon": None,
        "twelvedata": "WTI/USD",
        "mt5": "USOIL",
    },
}

_STOCK_MAP: Dict[str, Dict[str, str]] = {
    "AAPL": {
        "yfinance": "AAPL",
        "polygon": "AAPL",
        "twelvedata": "AAPL",
        "alphavantage": "AAPL",
        "mt5": "AAPL",
    },
    "TSLA": {
        "yfinance": "TSLA",
        "polygon": "TSLA",
        "twelvedata": "TSLA",
        "mt5": "TSLA",
    },
    "NVDA": {
        "yfinance": "NVDA",
        "polygon": "NVDA",
        "twelvedata": "NVDA",
        "mt5": "NVDA",
    },
    "MSFT": {
        "yfinance": "MSFT",
        "polygon": "MSFT",
        "twelvedata": "MSFT",
        "mt5": "MSFT",
    },
    "META": {
        "yfinance": "META",
        "polygon": "META",
        "twelvedata": "META",
        "mt5": "META",
    },
}

_INDEX_MAP: Dict[str, Dict[str, str]] = {
    "US500": {
        "yfinance": "^GSPC",
        "polygon": "I:SPX",
        "twelvedata": "SPX",
        "mt5": "US500",
    },
    "NAS100": {
        "yfinance": "^NDX",
        "polygon": "I:NDX",
        "twelvedata": "NDX",
        "mt5": "NAS100",
    },
    "US30": {
        "yfinance": "^DJI",
        "polygon": "I:DJI",
        "twelvedata": "DJI",
        "mt5": "US30",
    },
    "GER40": {
        "yfinance": "^GDAXI",
        "polygon": None,
        "twelvedata": "DAX",
        "mt5": "GER40",
    },
    "UK100": {
        "yfinance": "^FTSE",
        "polygon": None,
        "twelvedata": "FTSE",
        "mt5": "UK100",
    },
}

# Additional registry-backed instruments that previously drifted into the US
# equity default or had no deterministic provider mapping.
_INDEX_MAP.update({
    "JP225": {"yfinance": "^N225", "polygon": None, "twelvedata": "NIKKEI", "mt5": "JP225"},
    "FRA40": {"yfinance": "^FCHI", "polygon": None, "twelvedata": "CAC", "mt5": "FRA40"},
    "EU50": {"yfinance": "^STOXX50E", "polygon": None, "twelvedata": "STOXX50E", "mt5": "EU50"},
    "AUS200": {"yfinance": "^AXJO", "polygon": None, "twelvedata": "ASX200", "mt5": "AUS200"},
    "HK50": {"yfinance": "^HSI", "polygon": None, "twelvedata": "HSI", "mt5": "HK50"},
})
_COMMODITY_MAP.update({
    "WTI": {"yfinance": "CL=F", "polygon": None, "twelvedata": "WTI/USD", "mt5": "USOIL"},
    "BRENT": {"yfinance": "BZ=F", "polygon": None, "twelvedata": "BRENT/USD", "mt5": "UKOIL"},
})
_CRYPTO_MAP.update({
    "XAUTUSDT": {"binance": "XAUTUSDT", "coingecko": "tether-gold", "yfinance": "XAUT-USD", "polygon": None, "twelvedata": "XAUT/USD", "mt5": "XAUTUSD"},
})

# Combined lookup: canonical -> providers
_ALL_MAPS: Dict[str, Dict[str, str]] = {}
_ALL_MAPS.update(_CRYPTO_MAP)
_ALL_MAPS.update(_FX_MAP)
_ALL_MAPS.update(_COMMODITY_MAP)
_ALL_MAPS.update(_STOCK_MAP)
_ALL_MAPS.update(_INDEX_MAP)

# Asset class lookup
_ASSET_CLASS: Dict[str, str] = {}
for sym in _CRYPTO_MAP:
    _ASSET_CLASS[sym] = "crypto"
for sym in _FX_MAP:
    _ASSET_CLASS[sym] = "forex"
for sym in _COMMODITY_MAP:
    _ASSET_CLASS[sym] = "commodity"
for sym in _STOCK_MAP:
    _ASSET_CLASS[sym] = "stock"
for sym in _INDEX_MAP:
    _ASSET_CLASS[sym] = "index"


_ALIASES = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "BNBUSD": "BNBUSDT",
    "SP500": "US500",
    "SPX500": "US500",
    "S&P500": "US500",
    "US100": "NAS100",
    "USTEC": "NAS100",
    "DJ30": "US30",
    "DE40": "GER40",
    "DAX40": "GER40",
}


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    canonical_symbol: str
    asset_class: str
    tick_size: float
    session_calendar: str
    final_quote_kinds: tuple[str, ...]
    provider_symbols: Dict[str, Optional[str]]


def canonicalize_symbol(symbol: str) -> str:
    """Normalize aliases through the canonical asset registry."""
    return canonicalize_asset(symbol)


def classify_asset(symbol: str) -> str:
    """Return the registry-backed asset class without unsafe US-stock fallback."""
    return resolve_asset_spec(symbol).asset_class


def map_symbol(symbol: str, provider: str) -> Optional[str]:
    """Map a canonical symbol to the provider-specific format.

    Returns None if the provider doesn't support this asset.
    Falls back to the original symbol when no explicit mapping is defined.
    """
    s = canonicalize_symbol(symbol)
    p = provider.lower().strip()
    entry = _ALL_MAPS.get(s)
    if entry is not None:
        val = entry.get(p)
        # Explicit None means provider doesn't support this asset
        if val is None and p in entry:
            return None
        if val:
            return val
    # Generic fallback rules
    if p == "yfinance":
        cls = classify_asset(s)
        if cls == "crypto":
            base = s.replace("USDT", "").replace("USDC", "")
            return f"{base}-USD"
        if cls == "forex":
            if len(s) == 6:
                return f"{s}=X"
        return s
    if p == "polygon":
        cls = classify_asset(s)
        if cls == "crypto":
            base = s.replace("USDT", "").replace("USDC", "")
            return f"X:{base}USD"
        if cls == "forex":
            return f"C:{s}"
        return s
    if p == "twelvedata":
        cls = classify_asset(s)
        if cls == "forex" and len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        if cls == "crypto":
            base = s.replace("USDT", "").replace("USDC", "")
            return f"{base}/USD"
        return s
    if p == "oanda":
        cls = classify_asset(s)
        if cls == "forex" and len(s) == 6:
            return f"{s[:3]}_{s[3:]}"
        return s
    return s


def get_all_providers_for_asset(symbol: str) -> Dict[str, Optional[str]]:
    """Return a dict of {provider: symbol} for all known providers for this asset."""
    s = canonicalize_symbol(symbol)
    entry = _ALL_MAPS.get(s)
    if entry:
        return dict(entry)
    cls = classify_asset(s)
    if cls == "crypto":
        base = s.replace("USDT", "").replace("USDC", "")
        return {
            "binance": s,
            "coingecko": base.lower(),
            "yfinance": f"{base}-USD",
            "polygon": f"X:{base}USD",
            "twelvedata": f"{base}/USD",
            "mt5": f"{base}USD",
        }
    if cls == "forex":
        return {
            "yfinance": f"{s}=X" if len(s) == 6 else s,
            "polygon": f"C:{s}",
            "twelvedata": f"{s[:3]}/{s[3:]}" if len(s) == 6 else s,
            "mt5": s,
            "oanda": f"{s[:3]}_{s[3:]}" if len(s) == 6 else s,
        }
    if cls == "index":
        return {
            "yfinance": map_symbol(s, "yfinance"),
            "polygon": map_symbol(s, "polygon"),
            "twelvedata": map_symbol(s, "twelvedata"),
            "mt5": s,
        }
    # stock / commodity fallback
    return {
        "yfinance": s,
        "polygon": s,
        "twelvedata": s,
        "mt5": s,
    }


def get_instrument_spec(symbol: str) -> InstrumentSpec:
    """Return canonical mapping and final-quote capabilities for a symbol."""
    spec = resolve_asset_spec(symbol)
    tick_sizes = {
        "crypto": 0.00000001,
        "forex": 0.00001,
        "commodity": 0.01,
        "stock": 0.01,
        "index": 0.1,
        "macro": 0.01,
        "volatility": 0.01,
    }
    final_quote_kinds = () if spec.analysis_only or not spec.actionable else ("trade", "bid_ask", "ticker", "db_tick")
    return InstrumentSpec(
        canonical_symbol=spec.canonical_symbol,
        asset_class=spec.asset_class,
        tick_size=tick_sizes.get(spec.asset_class, 0.01),
        session_calendar=spec.session_calendar,
        final_quote_kinds=final_quote_kinds,
        provider_symbols=get_all_providers_for_asset(spec.canonical_symbol),
    )



__all__ = [
    "InstrumentSpec",
    "canonicalize_symbol",
    "classify_asset",
    "get_all_providers_for_asset",
    "get_instrument_spec",
    "map_symbol",
]
