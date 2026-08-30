"""Per-class market-universe construction with explicit degradation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Mapping

from core.asset_classes import AssetClass, canonical_asset_class
from services.asset_registry import build_asset_profile, normalize_symbol


@dataclass(frozen=True, slots=True)
class ClassUniverseHealth:
    asset_class: str
    configured_count: int
    discovered_count: int
    candle_capable_count: int
    usable_count: int
    source: str
    degraded: bool
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_class_complete_universe(
    database_symbols: Iterable[str],
    *,
    enabled_classes: Iterable[str],
    discoverers: Mapping[AssetClass, Callable[[], Iterable[str]]],
    candle_capable: Callable[[str, AssetClass], bool] | None = None,
) -> tuple[list[str], dict[str, ClassUniverseHealth]]:
    """Fill every enabled class independently; one healthy class masks nothing."""
    wanted = tuple(dict.fromkeys(canonical_asset_class(value) for value in enabled_classes))
    buckets: dict[AssetClass, list[str]] = {asset_class: [] for asset_class in wanted}
    for raw in database_symbols:
        symbol = normalize_symbol(raw)
        if not symbol:
            continue
        try:
            asset_class = canonical_asset_class(build_asset_profile(symbol).asset_class)
        except ValueError:
            continue
        if asset_class in buckets and symbol not in buckets[asset_class]:
            buckets[asset_class].append(symbol)

    output: list[str] = []
    health: dict[str, ClassUniverseHealth] = {}
    for asset_class in wanted:
        configured = list(buckets[asset_class])
        discovered: list[str] = []
        failure: str | None = None
        if not configured:
            producer = discoverers.get(asset_class)
            if producer is None:
                failure = "provider_not_configured"
            else:
                try:
                    for raw in producer() or ():
                        symbol = normalize_symbol(raw)
                        try:
                            classified = canonical_asset_class(build_asset_profile(symbol).asset_class)
                        except ValueError:
                            continue
                        if symbol and classified is asset_class and symbol not in discovered:
                            discovered.append(symbol)
                except Exception as exc:  # provider failure is evidence, not silence
                    failure = f"provider_failure:{type(exc).__name__}"
        candidates = configured or discovered
        usable = [symbol for symbol in candidates if candle_capable is None or candle_capable(symbol, asset_class)]
        if candidates and not usable:
            failure = failure or "no_candle_capable_instruments"
        if not candidates:
            failure = failure or "zero_usable_coverage"
        output.extend(usable)
        health[asset_class.value] = ClassUniverseHealth(
            asset_class=asset_class.value,
            configured_count=len(configured),
            discovered_count=len(discovered),
            candle_capable_count=len(usable),
            usable_count=len(usable),
            source="database" if configured else "provider_discovery" if discovered else "none",
            degraded=not bool(usable),
            failure_reason=failure,
        )
    return output, health


def default_discoverers() -> dict[AssetClass, Callable[[], Iterable[str]]]:
    from data.pair_discovery import (
        get_trending_commodity_tickers,
        get_trending_crypto_pairs,
        get_trending_fx_pairs,
        get_trending_index_tickers,
        get_trending_stock_tickers,
    )

    return {
        AssetClass.CRYPTO: lambda: get_trending_crypto_pairs(50),
        AssetClass.FOREX: get_trending_fx_pairs,
        AssetClass.EQUITY: lambda: get_trending_stock_tickers(30),
        AssetClass.INDEX: lambda: get_trending_index_tickers(20),
        AssetClass.COMMODITY: lambda: get_trending_commodity_tickers(20),
    }
