"""Venue-neutral provider contracts for staged SignalRankAI expansion.

The interfaces are capability declarations, not claims that a connector is
production-certified. Concrete adapters must pass connector-specific contract,
sandbox/testnet, restart-reconciliation and secret-leak tests before their
capabilities are marked certified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    EQUITY = "equity"
    ETF = "etf"
    COMMODITY = "commodity"
    INDEX = "index"
    OPTION = "option"
    FUTURE = "future"
    BOND = "bond"


class InstrumentKind(str, Enum):
    SPOT = "spot"
    MARGIN = "margin"
    PERPETUAL = "perpetual"
    DATED_FUTURE = "dated_future"
    OPTION = "option"
    CFD = "cfd"
    CASH_EQUITY = "cash_equity"


class CanonicalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Capability(str, Enum):
    INSTRUMENT_DISCOVERY = "instrument_discovery"
    HISTORICAL_OHLC = "historical_ohlc"
    LIVE_QUOTES = "live_quotes"
    TRADES = "trades"
    ORDER_BOOK_L1 = "order_book_l1"
    ORDER_BOOK_L2 = "order_book_l2"
    ORDER_BOOK_L3 = "order_book_l3"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATIONS = "liquidations"
    OPTIONS_CHAINS = "options_chains"
    GREEKS = "greeks"
    NEWS = "news"
    MACRO = "macro"
    ON_CHAIN = "on_chain"
    CORPORATE_ACTIONS = "corporate_actions"
    ECONOMIC_CALENDAR = "economic_calendar"
    ACCOUNT_STATE = "account_state"
    EXECUTION = "execution"
    POSITION_RECONCILIATION = "position_reconciliation"


class CertificationState(str, Enum):
    DECLARED = "declared"
    IMPLEMENTED = "implemented"
    SANDBOX_VERIFIED = "sandbox_verified"
    PRODUCTION_CERTIFIED = "production_certified"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class CanonicalInstrumentId:
    asset_class: AssetClass
    kind: InstrumentKind
    base: str
    quote: str | None = None
    settlement: str | None = None
    expiry: str | None = None
    strike: str | None = None
    option_right: str | None = None

    def key(self) -> str:
        parts = [self.asset_class.value, self.kind.value, self.base.upper()]
        for value in (self.quote, self.settlement, self.expiry, self.strike, self.option_right):
            parts.append(str(value or "-").upper())
        return ":".join(parts)


@dataclass(frozen=True, slots=True)
class UnsupportedCapability:
    provider: str
    capability: Capability
    reason: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class ProviderCapabilityManifest:
    provider: str
    capabilities: frozenset[Capability]
    asset_classes: frozenset[AssetClass]
    regions: frozenset[str] = frozenset()
    instrument_kinds: frozenset[InstrumentKind] = frozenset()
    rest: bool = False
    websocket: bool = False
    fix: bool = False
    paper_or_testnet: bool = False
    authentication_method: str | None = None
    required_permissions: tuple[str, ...] = ()
    order_types: tuple[str, ...] = ()
    ohlc_intervals: tuple[str, ...] = ()
    rate_limit_notes: str | None = None
    minimum_order_notes: str | None = None
    licensing_notes: str | None = None
    maintenance_status: str = "unknown"
    health_score: float | None = None
    certification: Mapping[Capability, CertificationState] = field(default_factory=dict)

    def supports(self, capability: Capability, *, certified_only: bool = False) -> bool:
        if capability not in self.capabilities:
            return False
        if not certified_only:
            return True
        return self.certification.get(capability) == CertificationState.PRODUCTION_CERTIFIED


@dataclass(frozen=True, slots=True)
class ProviderResult:
    value: Any | None = None
    unsupported: UnsupportedCapability | None = None
    provider: str = ""
    request_id: str | None = None
    source_timestamp: float | None = None
    received_timestamp: float | None = None

    @property
    def ok(self) -> bool:
        return self.unsupported is None and self.value is not None


@runtime_checkable
class CapabilityProvider(Protocol):
    @property
    def manifest(self) -> ProviderCapabilityManifest: ...


@runtime_checkable
class InstrumentDiscoveryProvider(CapabilityProvider, Protocol):
    async def discover_instruments(self) -> ProviderResult: ...


@runtime_checkable
class MarketDataProvider(CapabilityProvider, Protocol):
    async def fetch_ohlc(self, instrument: CanonicalInstrumentId, interval: str, *, limit: int) -> ProviderResult: ...


@runtime_checkable
class LiveQuoteProvider(CapabilityProvider, Protocol):
    async def fetch_live_quote(self, instrument: CanonicalInstrumentId) -> ProviderResult: ...


@runtime_checkable
class OrderBookProvider(CapabilityProvider, Protocol):
    async def fetch_order_book(self, instrument: CanonicalInstrumentId, *, depth: int) -> ProviderResult: ...


@runtime_checkable
class DerivativesDataProvider(CapabilityProvider, Protocol):
    async def fetch_derivatives_snapshot(self, instrument: CanonicalInstrumentId) -> ProviderResult: ...


@runtime_checkable
class NewsProvider(CapabilityProvider, Protocol):
    async def fetch_news(self, entities: Sequence[str], *, since: str | None = None) -> ProviderResult: ...


@runtime_checkable
class MacroDataProvider(CapabilityProvider, Protocol):
    async def fetch_macro_series(self, series: str, *, since: str | None = None) -> ProviderResult: ...


@runtime_checkable
class OnChainDataProvider(CapabilityProvider, Protocol):
    async def fetch_on_chain_metric(self, metric: str, asset: str) -> ProviderResult: ...


@runtime_checkable
class ExecutionVenue(CapabilityProvider, Protocol):
    async def submit_order(self, request: Mapping[str, Any]) -> ProviderResult: ...
    async def cancel_order(self, request: Mapping[str, Any]) -> ProviderResult: ...
    async def amend_order(self, request: Mapping[str, Any]) -> ProviderResult: ...


@runtime_checkable
class BrokerAccountProvider(CapabilityProvider, Protocol):
    async def fetch_account_state(self, account_id: str) -> ProviderResult: ...


@runtime_checkable
class PositionReconciliationProvider(CapabilityProvider, Protocol):
    async def reconcile_positions(self, account_id: str) -> ProviderResult: ...


@runtime_checkable
class CorporateActionsProvider(CapabilityProvider, Protocol):
    async def fetch_corporate_actions(self, instrument: CanonicalInstrumentId) -> ProviderResult: ...


@runtime_checkable
class EconomicCalendarProvider(CapabilityProvider, Protocol):
    async def fetch_economic_calendar(self, *, since: str, until: str) -> ProviderResult: ...


__all__ = [name for name in globals() if not name.startswith("_")]
