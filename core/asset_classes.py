"""Canonical asset-class vocabulary used at runtime boundaries."""

from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    EQUITY = "equity"
    INDEX = "index"
    COMMODITY = "commodity"


_ALIASES = {
    "crypto": AssetClass.CRYPTO,
    "crypto_spot": AssetClass.CRYPTO,
    "crypto_perpetual": AssetClass.CRYPTO,
    "crypto_futures": AssetClass.CRYPTO,
    "fx": AssetClass.FOREX,
    "forex": AssetClass.FOREX,
    "stock": AssetClass.EQUITY,
    "stocks": AssetClass.EQUITY,
    "equity": AssetClass.EQUITY,
    "indices": AssetClass.INDEX,
    "index": AssetClass.INDEX,
    "commodity_spot": AssetClass.COMMODITY,
    "commodity_future": AssetClass.COMMODITY,
    "commodities": AssetClass.COMMODITY,
    "commodity": AssetClass.COMMODITY,
}


def canonical_asset_class(value: object) -> AssetClass:
    if isinstance(value, AssetClass):
        return value
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return _ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported asset class: {value!r}") from exc


def engine_asset_class(value: object) -> str:
    """Compatibility value for older engine code; use only at its boundary."""
    canonical = canonical_asset_class(value)
    return {AssetClass.FOREX: "fx", AssetClass.EQUITY: "stock"}.get(canonical, canonical.value)
