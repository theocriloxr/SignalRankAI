"""Explicit strategy × asset-class × timeframe × regime capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.asset_classes import AssetClass, canonical_asset_class


ALL_REGIMES = frozenset({"TRENDING", "RANGING", "VOLATILE", "NEUTRAL", "UNKNOWN"})
ALL_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


@dataclass(frozen=True, slots=True)
class StrategyCapability:
    asset_classes: frozenset[AssetClass]
    timeframes: frozenset[str] = ALL_TIMEFRAMES
    regimes: frozenset[str] = ALL_REGIMES


_MARKETS = frozenset(AssetClass)
CAPABILITY_MATRIX: dict[str, StrategyCapability] = {
    "trend": StrategyCapability(_MARKETS),
    "momentum": StrategyCapability(_MARKETS),
    "volatility": StrategyCapability(_MARKETS),
    "structure": StrategyCapability(_MARKETS),
    "liquidity": StrategyCapability(_MARKETS),
    "fibonacci": StrategyCapability(_MARKETS),
    "tradingview": StrategyCapability(_MARKETS),
    "stock": StrategyCapability(frozenset({AssetClass.EQUITY}), frozenset({"15m", "1h", "4h", "1d"})),
}


def strategy_is_supported(group: str, asset_class: object, timeframe: str, regime: str) -> bool:
    capability = CAPABILITY_MATRIX.get(str(group).strip().lower())
    if capability is None:
        return False
    try:
        canonical = canonical_asset_class(asset_class)
    except ValueError:
        return False
    return (
        canonical in capability.asset_classes
        and str(timeframe).lower() in capability.timeframes
        and str(regime or "UNKNOWN").upper() in capability.regimes
    )


def supported_groups(groups: Iterable[str], asset_class: object, timeframe: str, regime: str) -> list[str]:
    return [group for group in groups if strategy_is_supported(group, asset_class, timeframe, regime)]
