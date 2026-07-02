from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


INDEX_SYMBOLS = {
    "US30", "DJI", "DOW", "US500", "SPX", "SPX500", "US100", "NAS100", "NDX",
    "RUSSELL2000", "RUT", "GER40", "DAX", "UK100", "FTSE", "FRA40", "CAC40",
    "JPN225", "NIKKEI", "HK50", "AUS200", "VIX",
}

COMMODITY_SYMBOLS = {
    "GOLD", "SILVER", "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "WTI", "USOIL",
    "BRENT", "UKOIL", "NATGAS", "CORN", "WHEAT", "SOYBEAN", "COFFEE", "COCOA",
    "SUGAR", "COTTON",
}

FX_CODES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "SEK", "NOK", "MXN", "ZAR", "TRY"}

DEFAULT_ASSET_SESSIONS: dict[str, tuple[str, ...]] = {
    "crypto": ("24/7", "London", "New York"),
    "fx": ("Tokyo", "London", "New York", "Overlap"),
    "forex": ("Tokyo", "London", "New York", "Overlap"),
    "commodity": ("London", "New York"),
    "index": ("London", "New York"),
    "indices": ("London", "New York"),
    "stock": ("New York",),
    "equity": ("New York",),
}


@dataclass(frozen=True, slots=True)
class AssetProfile:
    symbol: str
    canonical_symbol: str
    asset_class: str
    subclass: str
    aliases: tuple[str, ...] = ()
    sessions: tuple[str, ...] = ()
    preferred_timeframes: tuple[str, ...] = ()
    recommended_profiles: tuple[str, ...] = ()
    provider_symbols: dict[str, str | None] = field(default_factory=dict)
    broker_symbols: dict[str, str | None] = field(default_factory=dict)
    enabled: bool = True
    health_score: float = 75.0
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_symbol(symbol: Any) -> str:
    raw = str(symbol or "").upper().strip()
    raw = raw.replace("/", "").replace("-", "").replace("_", "")
    alias_map = {
        "BTCUSD": "BTCUSDT",
        "ETHUSD": "ETHUSDT",
        "XAU": "XAUUSD",
        "GOLD": "XAUUSD",
        "SILVER": "XAGUSD",
        "US500": "SPX500",
        "US100": "NAS100",
    }
    return alias_map.get(raw, raw)


def classify_asset(symbol: Any) -> str:
    sym = normalize_symbol(symbol)
    if not sym:
        return "unknown"
    if sym in INDEX_SYMBOLS:
        return "index"
    if sym in COMMODITY_SYMBOLS:
        return "commodity"
    if sym.endswith(("USDT", "USDC", "BUSD")) or sym in {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA"}:
        return "crypto"
    if len(sym) == 6 and sym[:3] in FX_CODES and sym[3:] in FX_CODES:
        return "fx"
    if sym.startswith(("EQUITY:", "STOCK:")):
        return "stock"
    return "stock"


def _subclass(symbol: str, asset_class: str) -> str:
    if asset_class == "crypto":
        base = symbol.replace("USDT", "").replace("USDC", "")
        return "large_cap" if base in {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"} else "altcoin"
    if asset_class == "fx":
        return "major" if symbol in {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"} else "minor_or_exotic"
    if asset_class == "commodity":
        if symbol in {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}:
            return "metal"
        if symbol in {"WTI", "USOIL", "BRENT", "UKOIL", "NATGAS"}:
            return "energy"
        return "agriculture"
    if asset_class == "index":
        if symbol in {"US30", "DJI", "SPX500", "SPX", "NAS100", "NDX", "RUSSELL2000", "RUT"}:
            return "us_index"
        if symbol in {"GER40", "UK100", "FRA40"}:
            return "europe_index"
        return "global_index"
    return "equity"


def _recommended_profiles(asset_class: str, symbol: str) -> tuple[str, ...]:
    if asset_class in {"crypto", "fx"}:
        return ("scalp", "day", "swing")
    if asset_class in {"commodity", "index"}:
        return ("day", "swing", "position")
    return ("day", "swing", "position")


def _preferred_timeframes(asset_class: str) -> tuple[str, ...]:
    if asset_class == "crypto":
        return ("1m", "5m", "15m", "1h", "4h")
    if asset_class == "fx":
        return ("5m", "15m", "1h", "4h")
    if asset_class in {"commodity", "index"}:
        return ("5m", "15m", "1h", "4h", "1d")
    return ("15m", "1h", "4h", "1d")


def build_asset_profile(symbol: Any, provider_symbols: dict[str, str | None] | None = None) -> AssetProfile:
    canonical = normalize_symbol(symbol)
    asset_class = classify_asset(canonical)
    aliases = tuple(sorted({str(symbol or "").upper().strip(), canonical} - {""}))
    try:
        from services.asset_mapper import get_all_providers_for_asset

        mapped = get_all_providers_for_asset(canonical)
    except Exception:
        mapped = {}
    if provider_symbols:
        mapped.update(provider_symbols)
    return AssetProfile(
        symbol=canonical,
        canonical_symbol=canonical,
        asset_class=asset_class,
        subclass=_subclass(canonical, asset_class),
        aliases=aliases,
        sessions=DEFAULT_ASSET_SESSIONS.get(asset_class, ("New York",)),
        preferred_timeframes=_preferred_timeframes(asset_class),
        recommended_profiles=_recommended_profiles(asset_class, canonical),
        provider_symbols=mapped,
        broker_symbols={"mt5": mapped.get("mt5") or canonical, "binance": mapped.get("binance"), "bybit": canonical if asset_class == "crypto" else None},
        enabled=canonical not in _disabled_assets(),
    )


def _disabled_assets() -> set[str]:
    raw = os.getenv("DISABLED_ASSETS", "")
    return {normalize_symbol(x) for x in raw.split(",") if x.strip()}


def discover_asset_universe(limit_per_class: int = 25) -> list[AssetProfile]:
    """Build the current tradable universe from provider discovery plus stable fallbacks."""
    symbols: list[str] = []
    try:
        from data.pair_discovery import (
            get_trending_crypto_pairs,
            get_trending_fx_pairs,
            get_trending_stock_tickers,
            get_trending_commodity_tickers,
            get_trending_index_tickers,
        )

        for fn in (
            get_trending_crypto_pairs,
            get_trending_fx_pairs,
            get_trending_commodity_tickers,
            get_trending_index_tickers,
            get_trending_stock_tickers,
        ):
            try:
                symbols.extend(fn(limit_per_class) or [])
            except Exception:
                continue
    except Exception:
        pass
    if not symbols:
        symbols = [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "EURUSD", "GBPUSD", "USDJPY",
            "XAUUSD", "XAGUSD", "SPX500", "NAS100", "US30", "AAPL", "NVDA",
        ]
    profiles: list[AssetProfile] = []
    seen: set[str] = set()
    for symbol in symbols:
        profile = build_asset_profile(symbol)
        if profile.canonical_symbol in seen or not profile.enabled:
            continue
        seen.add(profile.canonical_symbol)
        profiles.append(profile)
    return profiles


def filter_profiles(
    profiles: Iterable[AssetProfile],
    *,
    asset_classes: Iterable[str] | None = None,
    trade_profile: str | None = None,
) -> list[AssetProfile]:
    wanted_classes = {str(x).lower().strip() for x in (asset_classes or []) if str(x).strip()}
    wanted_profile = str(trade_profile or "").lower().strip()
    out: list[AssetProfile] = []
    for profile in profiles:
        if wanted_classes and profile.asset_class not in wanted_classes:
            continue
        if wanted_profile and wanted_profile != "all" and wanted_profile not in profile.recommended_profiles:
            continue
        out.append(profile)
    return out
