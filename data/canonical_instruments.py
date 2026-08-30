"""Canonical instrument model and normalization helpers.

Builds on ``data.provider_contracts.CanonicalInstrumentId`` by adding the full
trading/calibration surface (tick size, quantity step, minimums, calendar,
status, aliases) plus pure normalization helpers for symbol aliases, status
changes and corporate-action price adjustments. No I/O: adapters populate and
resolve these records from their own discovery/reference sources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Mapping

from data.provider_contracts import AssetClass, CanonicalInstrumentId, InstrumentKind


class InstrumentStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    RENAMED = "renamed"
    MIGRATED = "migrated"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class PositionMode(str, Enum):
    ONE_WAY = "one_way"
    HEDGE = "hedge"


class MarginMode(str, Enum):
    CROSS = "cross"
    ISOLATED = "isolated"


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"non_finite_{field_name}") from None
    if not parsed.is_finite():
        raise ValueError(f"non_finite_{field_name}")
    return parsed


@dataclass(frozen=True, slots=True)
class CanonicalInstrument:
    """Full canonical instrument record used by routing, sizing and delivery."""

    id: CanonicalInstrumentId
    venue: str
    provider_symbol: str
    status: InstrumentStatus = InstrumentStatus.ACTIVE
    contract_multiplier: Decimal = Decimal("1")
    linear_or_inverse: str = "linear"  # linear | inverse
    expiry: str | None = None
    strike: str | None = None
    option_type: str | None = None
    tick_size: Decimal | None = None
    quantity_step: Decimal | None = None
    minimum_quantity: Decimal | None = None
    minimum_notional: Decimal | None = None
    trading_calendar: str = "24x7"
    timezone: str = "UTC"
    position_mode: PositionMode = PositionMode.ONE_WAY
    margin_modes: tuple[MarginMode, ...] = (MarginMode.ISOLATED,)
    aliases: tuple[str, ...] = ()
    previous_symbol: str | None = None

    def __post_init__(self) -> None:
        if _decimal(self.contract_multiplier, "contract_multiplier") <= 0:
            raise ValueError("contract_multiplier_must_be_positive")
        for attr in ("tick_size", "quantity_step", "minimum_quantity", "minimum_notional"):
            value = getattr(self, attr)
            if value is not None:
                parsed = _decimal(value, attr)
                if parsed < 0:
                    raise ValueError(f"{attr}_must_not_be_negative")
                object.__setattr__(self, attr, parsed)
        object.__setattr__(self, "venue", str(self.venue or "unknown").lower())
        object.__setattr__(self, "provider_symbol", str(self.provider_symbol or "").upper())
        object.__setattr__(self, "aliases", tuple(sorted({a.upper() for a in self.aliases if a})))

    @property
    def canonical_key(self) -> str:
        return self.id.key()

    def matches_alias(self, symbol: str) -> bool:
        probe = str(symbol or "").upper().strip()
        return probe == self.provider_symbol or probe in self.aliases

    def price_after_split(self, *, price: object, split_ratio: object) -> Decimal:
        """Adjusted price after a corporate action.

        ``split_ratio`` is expressed as new/old (2 = 2-for-1 split). A reverse
        split (1-for-2) passes 0.5. Returns an unrounded Decimal.
        """
        price_d = _decimal(price, "price")
        ratio = _decimal(split_ratio, "split_ratio")
        if ratio <= 0:
            raise ValueError("split_ratio_must_be_positive")
        if price_d < 0:
            raise ValueError("price_must_not_be_negative")
        return price_d / ratio


#: Simple alias normalizer: strips whitespace and common separators, uppercases.
_SYMBOL_SEPARATORS = re.compile(r"[\s_\-/]+")


def normalize_symbol(symbol: str) -> str:
    """Canonical symbol spelling: separators stripped, uppercased."""
    return _SYMBOL_SEPARATORS.sub("", str(symbol or "")).upper().strip()


@dataclass(frozen=True, slots=True)
class InstrumentRegistry:
    """In-memory canonical instrument registry with alias resolution."""

    instruments: Mapping[str, CanonicalInstrument] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        resolved: dict[str, str] = {}
        for key, instrument in self.instruments.items():
            for alias in (instrument.provider_symbol, *instrument.aliases):
                normalized = normalize_symbol(alias)
                if normalized:
                    resolved[normalized] = key
        resolved.update({normalize_symbol(k): k for k in self.instruments})
        object.__setattr__(self, "aliases", resolved)

    def resolve(self, symbol: str) -> CanonicalInstrument | None:
        key = self.aliases.get(normalize_symbol(symbol))
        return self.instruments.get(key) if key else None

    def active(self) -> tuple[CanonicalInstrument, ...]:
        return tuple(i for i in self.instruments.values() if i.status is InstrumentStatus.ACTIVE)

    def by_asset_class(self, asset_class: AssetClass) -> tuple[CanonicalInstrument, ...]:
        return tuple(i for i in self.instruments.values() if i.id.asset_class is asset_class)


def direction_canonical(value: str) -> str:
    """Normalize BUY/LONG and SELL/SHORT to canonical long/short."""
    probe = str(value or "").strip().upper()
    if probe in ("BUY", "LONG", "L"):
        return "long"
    if probe in ("SELL", "SHORT", "S"):
        return "short"
    raise ValueError(f"unknown_direction:{probe}")


__all__ = [
    "CanonicalInstrument",
    "InstrumentRegistry",
    "InstrumentStatus",
    "MarginMode",
    "PositionMode",
    "direction_canonical",
    "normalize_symbol",
]
