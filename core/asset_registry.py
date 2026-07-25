"""Canonical instrument registry used by routing, sessions, and diagnostics.

The registry deliberately separates *classification* from *actionability*.
Macro/yield/volatility instruments may be useful context without being valid
trade-delivery instruments. Unknown symbols fail closed instead of silently
receiving US equity market hours.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AssetSpec:
    canonical_symbol: str
    asset_class: str
    subtype: str
    timezone: str
    session_calendar: str
    continuous: bool = False
    actionable: bool = True
    analysis_only: bool = False
    aliases: tuple[str, ...] = ()
    provider_symbols: Mapping[str, str | None] = field(default_factory=dict)


_SPECS: dict[str, AssetSpec] = {}
_ALIASES: dict[str, str] = {}


def _register(spec: AssetSpec) -> None:
    _SPECS[spec.canonical_symbol] = spec
    for alias in (spec.canonical_symbol, *spec.aliases):
        _ALIASES[_compact(alias)] = spec.canonical_symbol


def _compact(symbol: str) -> str:
    raw = str(symbol or "").upper().strip()
    if ":" in raw:
        prefix, value = raw.split(":", 1)
        if prefix in {"CRYPTO", "FX", "FOREX", "FORX", "COMMODITY", "EQUITY", "STOCK", "INDEX", "MACRO"}:
            raw = value
    if raw.startswith("^"):
        return raw
    return raw.replace("/", "").replace("_", "").replace("-", "")


# Crypto and tokenised commodities.
for symbol, aliases in {
    "BTCUSDT": ("BTCUSD", "BTC-USD"),
    "ETHUSDT": ("ETHUSD", "ETH-USD"),
    "BNBUSDT": ("BNBUSD", "BNB-USD"),
    "SOLUSDT": ("SOLUSD", "SOL-USD"),
    "XRPUSDT": ("XRPUSD", "XRP-USD"),
}.items():
    _register(AssetSpec(symbol, "crypto", "crypto_stablecoin", "UTC", "crypto_24_7", True, aliases=aliases))

_register(AssetSpec("USDTIDR", "crypto", "crypto_fiat", "UTC", "crypto_24_7", True))
_register(AssetSpec("DOGEIDR", "crypto", "crypto_fiat", "UTC", "crypto_24_7", True))
_register(AssetSpec("USDTARS", "crypto", "crypto_fiat", "UTC", "crypto_24_7", True))
_register(AssetSpec("XAUTUSDT", "crypto", "tokenised_commodity", "UTC", "crypto_24_7", True, aliases=("XAUTUSD",)))

# FX majors and selected liquid crosses.
for symbol in (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
):
    _register(AssetSpec(symbol, "forex", "fx_spot", "UTC", "fx_24_5"))

# Metals and energy.
_register(AssetSpec("XAUUSD", "commodity", "metal", "UTC", "commodity_23_5", aliases=("GOLD",)))
_register(AssetSpec("XAGUSD", "commodity", "metal", "UTC", "commodity_23_5", aliases=("SILVER",)))
_register(AssetSpec("WTI", "commodity", "energy", "UTC", "commodity_23_5", aliases=("OIL", "USOIL")))
_register(AssetSpec("BRENT", "commodity", "energy", "UTC", "commodity_23_5", aliases=("UKOIL",)))
_register(AssetSpec("NATGAS", "commodity", "energy", "UTC", "commodity_23_5"))

# US and international indices. These are mapped to explicit regional sessions,
# never the US cash calendar by accident.
_register(AssetSpec("US500", "index", "index_cfd", "America/New_York", "us_equity", aliases=("SP500", "SPX500", "SPX", "GSPC", "^GSPC")))
_register(AssetSpec("NAS100", "index", "index_cfd", "America/New_York", "us_equity", aliases=("US100", "USTEC", "NDX", "^NDX")))
_register(AssetSpec("US30", "index", "index_cfd", "America/New_York", "us_equity", aliases=("DJ30", "DJI", "^DJI")))
_register(AssetSpec("GER40", "index", "index_cfd", "Europe/Berlin", "europe_equity", aliases=("DE40", "DAX40", "^GDAXI")))
_register(AssetSpec("UK100", "index", "index_cfd", "Europe/London", "uk_equity", aliases=("FTSE", "^FTSE")))
_register(AssetSpec("JP225", "index", "index_cfd", "Asia/Tokyo", "japan_equity", aliases=("JPN225", "NIKKEI", "^N225")))
_register(AssetSpec("FRA40", "index", "index_cfd", "Europe/Paris", "europe_equity", aliases=("CAC40", "^FCHI")))
_register(AssetSpec("EU50", "index", "index_cfd", "Europe/Paris", "europe_equity", aliases=("STOXX50", "^STOXX50E")))
_register(AssetSpec("AUS200", "index", "index_cfd", "Australia/Sydney", "australia_equity", aliases=("ASX200", "^AXJO")))
_register(AssetSpec("HK50", "index", "index_cfd", "Asia/Hong_Kong", "hong_kong_equity", aliases=("HSI", "^HSI")))

# Context-only macro instruments. A tradeable proxy must be configured before
# they can become actionable.
_register(AssetSpec("DXY", "macro", "currency_index", "UTC", "macro_analysis", False, False, True, aliases=("DX-Y.NYB",)))
_register(AssetSpec("US10Y", "macro", "treasury_yield", "UTC", "macro_analysis", False, False, True, aliases=("TNX", "^TNX")))
_register(AssetSpec("US02Y", "macro", "treasury_yield", "UTC", "macro_analysis", False, False, True, aliases=("IRX", "^IRX")))
_register(AssetSpec("VIX", "volatility", "volatility_index", "America/New_York", "us_equity", False, False, True, aliases=("^VIX",)))


_FIAT = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "IDR", "ARS",
    "HKD", "SGD", "SEK", "NOK", "ZAR", "TRY", "MXN", "BRL",
}
_CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "DOT", "MATIC", "AVAX",
    "LTC", "LINK", "ATOM", "TRX", "XLM", "UNI", "AAVE", "USDT", "USDC", "XAUT",
}
_STABLE_QUOTES = {"USDT", "USDC", "BUSD", "DAI", "BTC", "ETH"}


def canonicalize_asset(symbol: str) -> str:
    raw = str(symbol or "").upper().strip()
    if ":" in raw:
        prefix, value = raw.split(":", 1)
        if prefix in {"CRYPTO", "FX", "FOREX", "FORX", "COMMODITY", "EQUITY", "STOCK", "INDEX", "MACRO"}:
            raw = value
    compact = _compact(raw)
    mapped = _ALIASES.get(compact)
    if mapped is not None:
        return mapped
    # Preserve canonical exchange punctuation for equities such as BRK-B and
    # BF.B. Crypto aliases are resolved above before this conservative path.
    equity_chars = raw.replace(".", "").replace("-", "")
    if raw and equity_chars.isalpha() and 1 <= len(equity_chars) <= 6:
        return raw
    return compact


def resolve_asset_spec(symbol: str, *, allow_dynamic_equity: bool = True) -> AssetSpec:
    canonical = canonicalize_asset(symbol)
    explicit = _SPECS.get(canonical)
    if explicit is not None:
        return explicit

    # Dynamic crypto/stablecoin and crypto/fiat pairs.
    for quote in sorted(_STABLE_QUOTES | _FIAT, key=len, reverse=True):
        if canonical.endswith(quote) and len(canonical) > len(quote):
            base = canonical[: -len(quote)]
            if base in _CRYPTO_BASES or quote in _STABLE_QUOTES:
                subtype = "crypto_fiat" if quote in _FIAT and quote != "USD" else "crypto_stablecoin"
                return AssetSpec(canonical, "crypto", subtype, "UTC", "crypto_24_7", True)

    # Dynamic FX only when both sides are recognised fiat currencies.
    if len(canonical) == 6 and canonical[:3] in _FIAT and canonical[3:] in _FIAT:
        return AssetSpec(canonical, "forex", "fx_spot", "UTC", "fx_24_5")

    # Conservative dynamic US equity support. Pair-like or numeric symbols do
    # not enter this path, preventing noisy crypto-fiat/index aliases from being
    # treated as US stocks.
    raw = str(symbol or "").upper().strip()
    equity_chars = raw.replace(".", "").replace("-", "")
    if allow_dynamic_equity and 1 <= len(equity_chars) <= 6 and equity_chars.isalpha():
        return AssetSpec(raw, "stock", "us_equity", "America/New_York", "us_equity")

    return AssetSpec(canonical, "unknown", "unknown", "UTC", "unsupported", False, False, False)


def get_asset_spec(symbol: str) -> AssetSpec:
    return resolve_asset_spec(symbol)


def list_asset_specs() -> tuple[AssetSpec, ...]:
    return tuple(_SPECS[key] for key in sorted(_SPECS))


__all__ = [
    "AssetSpec",
    "canonicalize_asset",
    "get_asset_spec",
    "list_asset_specs",
    "resolve_asset_spec",
]
