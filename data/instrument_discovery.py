"""Dynamic provider-driven instrument discovery and canonical registry.

The engine universe is built from provider discovery responses instead of
hardcoded symbol arrays (provider addendum: "Dynamic Provider Asset Discovery
and Instrument Registry").  Hardcoded lists remain only as emergency fallback,
owner-pinned instruments, bootstrap symbols and allow/block lists.

Key properties:

* Providers are the authoritative source of ``ProviderInstrument`` rows.
* Rows are normalized into ``CanonicalInstrument`` records (identity includes
  asset class + instrument type, so tokenized gold ``XAUTUSDT`` and commodity
  gold ``XAUUSD`` stay separate instruments sharing an underlying group).
* ``provider_symbol -> canonical -> {provider: provider_symbol}`` maps are
  maintained for delivery-time routing.
* One provider failing never blocks discovery from the others.
* Discovery is idempotent and restart-safe (pure ingestion into an explicit
  registry).

This module performs no I/O itself; adapters own HTTP.  ``run_discovery`` only
calls adapter callables with isolation, timeouts and per-provider cooldowns.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

from data.canonical_instruments import CanonicalInstrument, InstrumentStatus, normalize_symbol
from data.provider_activation import ProviderActivation, ProviderActivationState, resolve_activation
from data.provider_contracts import AssetClass, CanonicalInstrumentId, InstrumentKind

logger = logging.getLogger(__name__)

#: Default scan-priority ordering by asset class (dynamic priority may override).
_ASSET_CLASS_PRIORITY = {
    "crypto": 10,
    "forex": 20,
    "commodity": 30,
    "equity": 40,
    "etf": 41,
    "index": 50,
    "option": 60,
    "future": 61,
    "bond": 70,
    "interest_rate": 71,
    "volatility": 72,
    "onchain_pool": 80,
}

_ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "crypto": AssetClass.CRYPTO,
    "crypto_spot": AssetClass.CRYPTO,
    "crypto_perpetual": AssetClass.CRYPTO,
    "forex": AssetClass.FOREX,
    "fx": AssetClass.FOREX,
    "equity": AssetClass.EQUITY,
    "stock": AssetClass.EQUITY,
    "etf": AssetClass.ETF,
    "commodity": AssetClass.COMMODITY,
    "index": AssetClass.INDEX,
    "indices": AssetClass.INDEX,
    "option": AssetClass.OPTION,
    "future": AssetClass.FUTURE,
    "futures": AssetClass.FUTURE,
    "bond": AssetClass.BOND,
    "interest_rate": AssetClass.BOND,
    "volatility": AssetClass.INDEX,
    "onchain_pool": AssetClass.CRYPTO,
    "macro": AssetClass.INDEX,
}

_KIND_MAP: dict[str, InstrumentKind] = {
    "spot": InstrumentKind.SPOT,
    "perpetual": InstrumentKind.PERPETUAL,
    "swap": InstrumentKind.PERPETUAL,
    "future": InstrumentKind.DATED_FUTURE,
    "futures": InstrumentKind.DATED_FUTURE,
    "dated_future": InstrumentKind.DATED_FUTURE,
    "option": InstrumentKind.OPTION,
    "options": InstrumentKind.OPTION,
    "cfd": InstrumentKind.CFD,
    "margin": InstrumentKind.MARGIN,
    "equity": InstrumentKind.CASH_EQUITY,
    "stock": InstrumentKind.CASH_EQUITY,
    "cash_equity": InstrumentKind.CASH_EQUITY,
    "yield_series": InstrumentKind.CFD,
    "dex_pool": InstrumentKind.SPOT,
    "stablecoin": InstrumentKind.SPOT,
    "on_chain": InstrumentKind.SPOT,
}

_INSTRUMENT_TYPE_TO_ASSET_CLASS: dict[str, str] = {
    "crypto_perpetual": "crypto",
    "crypto_dated_future": "crypto",
    "crypto_option": "crypto",
    "equity_option": "equity",
    "index_future": "index",
    "index_option": "index",
    "commodity_future": "commodity",
    "commodity_cfd": "commodity",
    "fx_cfd": "forex",
    "tokenized_real_world_asset": "crypto",
    "onchain_pool": "onchain_pool",
}


@dataclass(frozen=True, slots=True)
class ProviderInstrument:
    """One discovered instrument from one provider."""

    provider: str
    venue: str
    provider_symbol: str
    asset_class: str
    instrument_type: str
    base: str
    quote: Optional[str] = None
    settlement: Optional[str] = None
    market_status: str = "active"
    tradable: bool = True
    capabilities: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return str(self.market_status or "").lower() in {"active", "open", "trading", ""}


@dataclass(frozen=True, slots=True)
class DiscoveryRunResult:
    provider: str
    started_at: float
    duration_ms: float
    discovered: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    mapping_failures: int = 0
    state: str = "ok"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "state": self.state,
            "reason": self.reason,
            "discovered": self.discovered,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "mapping_failures": self.mapping_failures,
            "duration_ms": round(self.duration_ms, 1),
        }


class DynamicInstrumentRegistry:
    """In-memory canonical registry fed by provider discovery.

    Thread-safe ingestion; the registry is the runtime universe source.
    """

    def __init__(self) -> None:
        self._instruments: dict[str, CanonicalInstrument] = {}
        self._by_provider: dict[str, dict[str, CanonicalInstrument]] = {}
        self._provider_symbols: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self.metrics: Counter[str] = Counter()

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    def ingest(
        self,
        provider: str,
        rows: Iterable[Mapping[str, Any]] | Iterable[ProviderInstrument],
    ) -> DiscoveryRunResult:
        started = time.monotonic()
        provider = str(provider or "unknown").lower().strip()
        discovered = created = updated = unchanged = mapping_failures = 0
        with self._lock:
            for row in rows:
                discovered += 1
                instrument = self._canonicalize(provider, row)
                if instrument is None:
                    mapping_failures += 1
                    continue
                key = instrument.canonical_key
                if key in self._instruments:
                    if self._instruments[key] == instrument:
                        unchanged += 1
                    else:
                        self._instruments[key] = instrument
                        updated += 1
                else:
                    self._instruments[key] = instrument
                    created += 1
                self._by_provider.setdefault(provider, {})[key] = instrument
                self._provider_symbols.setdefault(provider, {})[key] = instrument.provider_symbol
        result = DiscoveryRunResult(
            provider=provider,
            started_at=time.time(),
            duration_ms=(time.monotonic() - started) * 1000.0,
            discovered=discovered,
            created=created,
            updated=updated,
            unchanged=unchanged,
            mapping_failures=mapping_failures,
        )
        self.metrics["instruments_discovered"] += result.discovered
        self.metrics["instruments_created"] += created
        self.metrics["symbol_mapping_failures"] += result.mapping_failures
        return result

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def resolve(self, symbol: str) -> Optional[CanonicalInstrument]:
        """Resolve a symbol (any spelling/provider alias) to a canonical instrument."""
        probe = normalize_symbol(symbol)
        with self._lock:
            for instrument in self._instruments.values():
                if instrument.matches_alias(probe):
                    return instrument
            # Cross-provider symbol match: the probe equals another provider's
            # listing symbol for the same canonical instrument.
            for key, provider_symbol in self._all_provider_symbols().items():
                if normalize_symbol(provider_symbol) == probe:
                    return self._instruments.get(key)
            return None

    def resolve_with_provider(self, symbol: str, provider: str) -> Optional[CanonicalInstrument]:
        probe = normalize_symbol(symbol)
        with self._lock:
            mapping = self._provider_symbols.get(str(provider).lower(), {})
            for key, provider_symbol in mapping.items():
                if normalize_symbol(provider_symbol) == probe:
                    return self._instruments.get(key)
        return self.resolve(symbol)

    def _all_provider_symbols(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for mapping in self._provider_symbols.values():
            out.update(mapping)
        return out

    def provider_map(self, symbol: str) -> dict[str, str]:
        """``{provider: provider_symbol}`` for every provider listing `symbol`."""
        probe = normalize_symbol(symbol)
        out: dict[str, str] = {}
        with self._lock:
            for provider, mapping in self._provider_symbols.items():
                for key, provider_symbol in mapping.items():
                    if key == probe:
                        out[provider] = provider_symbol
                        break
                    instrument = self._instruments.get(key)
                    if instrument is not None and instrument.matches_alias(probe):
                        out[provider] = provider_symbol
                        break
        return out

    def by_provider(self, provider: str) -> tuple[CanonicalInstrument, ...]:
        with self._lock:
            return tuple(self._by_provider.get(str(provider).lower(), {}).values())

    def all(self) -> tuple[CanonicalInstrument, ...]:
        with self._lock:
            return tuple(self._instruments.values())

    def universe(
        self,
        *,
        asset_classes: Iterable[str] | None = None,
        tradable_only: bool = True,
        min_providers: int = 1,
        active_only: bool = True,
    ) -> tuple[CanonicalInstrument, ...]:
        """Selection SQL for the engine universe (bounded, gated)."""
        wanted = {str(a).lower() for a in (asset_classes or ())} or None
        with self._lock:
            candidates = list(self._instruments.values())
        out = []
        for instrument in candidates:
            asset_class = instrument.id.asset_class.value
            if wanted and asset_class not in wanted and str(instrument.id.asset_class.name).lower() not in wanted:
                continue
            if active_only and instrument.status is not InstrumentStatus.ACTIVE:
                continue
            if tradable_only and not self._tradable(instrument):
                continue
            if min_providers > 1 and len(self._providers_for(instrument.canonical_key)) < min_providers:
                continue
            out.append(instrument)
        out.sort(
            key=lambda i: (
                _ASSET_CLASS_PRIORITY.get(i.id.asset_class.value, 100),
                i.id.base,
            )
        )
        return tuple(out)

    def count(self) -> int:
        with self._lock:
            return len(self._instruments)

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self.metrics)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _providers_for(self, key: str) -> list[str]:
        out = []
        for provider, mapping in self._by_provider.items():
            if key in mapping:
                out.append(provider)
        return out

    @staticmethod
    def _tradable(instrument: CanonicalInstrument) -> bool:
        return instrument.status is InstrumentStatus.ACTIVE

    @classmethod
    def _canonicalize(
        cls, provider: str, row: Mapping[str, Any] | ProviderInstrument
    ) -> Optional[CanonicalInstrument]:
        if isinstance(row, ProviderInstrument):
            data: Mapping[str, Any] = {
                "provider": row.provider,
                "venue": row.venue,
                "provider_symbol": row.provider_symbol,
                "asset_class": row.asset_class,
                "instrument_type": row.instrument_type,
                "base": row.base,
                "quote": row.quote,
                "settlement": row.settlement,
                "market_status": row.market_status,
                "tradable": row.tradable,
            }
        else:
            data = dict(row or {})
        if not isinstance(data, Mapping):
            return None
        try:
            provider_symbol = str(data.get("provider_symbol") or data.get("symbol") or "").strip().upper()
            base = str(data.get("base") or "").strip().upper()
            if not provider_symbol or not base:
                return None
            quote = str(data.get("quote") or "USDT").strip().upper() or None
            instrument_type = str(data.get("instrument_type") or "spot").lower()
            asset_class = cls._asset_class_for(data, instrument_type)
            kind = _KIND_MAP.get(instrument_type, InstrumentKind.SPOT)
            instrument_id = CanonicalInstrumentId(
                asset_class=asset_class,
                kind=kind,
                base=base,
                quote=quote,
                settlement=str(data.get("settlement") or quote or "").upper() or None,
            )
            market_status = str(data.get("market_status") or "active").lower()
            status = (
                InstrumentStatus.ACTIVE
                if market_status in {"active", "open", "trading", ""}
                else (
                    InstrumentStatus.SUSPENDED
                    if market_status in {"suspended", "halted", "closed"}
                    else InstrumentStatus.DELISTED
                )
            )
            return CanonicalInstrument(
                id=instrument_id,
                venue=str(data.get("venue") or provider or "unknown").lower(),
                provider_symbol=provider_symbol,
                status=status,
                aliases=tuple(str(data.get("aliases") or "").split(",")),
                expiry=str(data.get("expiry") or "") or None,
                strike=str(data.get("strike") or "") or None,
                option_type=str(data.get("option_type") or "") or None,
            )
        except Exception as exc:  # noqa: BLE001 - record-level isolation
            logger.debug("instrument mapping failure provider=%s row=%r: %s", provider, data, exc)
            return None

    @staticmethod
    def _asset_class_for(data: Mapping[str, Any], instrument_type: str) -> AssetClass:
        explicit = str(data.get("asset_class") or "").lower()
        if explicit:
            mapped = _ASSET_CLASS_MAP.get(explicit)
            if mapped is not None:
                return mapped
        implicit = _INSTRUMENT_TYPE_TO_ASSET_CLASS.get(instrument_type)
        if implicit:
            mapped = _ASSET_CLASS_MAP.get(implicit)
            if mapped is not None:
                return mapped
        return AssetClass.CRYPTO


#: Module-level per-provider cooldowns so repeated scheduler invocations of
#: ``run_discovery`` share one rate-limit budget (like the engine's resend
#: cursor, the discovery cursor is process-lifetime state).
_DISCOVERY_COOLDOWNS: dict[str, float] = {}


def run_discovery(
    providers: Mapping[str, Callable[[], Iterable[Mapping[str, Any]]] | Callable[..., Iterable[Mapping[str, Any]]]],
    *,
    registry: DynamicInstrumentRegistry | None = None,
    min_interval_seconds: float = 900.0,
    top: int = 100,
) -> dict[str, DiscoveryRunResult]:
    """Run discovery for every enabled provider with isolation and cooldowns.

    ``providers`` maps provider key -> discovery callable returning rows.
    One provider raising/timeouting is recorded and never aborts the others.
    """
    registry = registry or DynamicInstrumentRegistry()
    results: dict[str, DiscoveryRunResult] = {}

    for provider, callable_fn in providers.items():
        provider = str(provider).lower().strip()
        last = _DISCOVERY_COOLDOWNS.get(provider, 0.0)
        if last > time.monotonic():
            results[provider] = DiscoveryRunResult(
                provider=provider, started_at=time.time(), duration_ms=0.0,
                state="cooldown", reason="discovery_rate_limit",
            )
            continue
        started = time.monotonic()
        try:
            rows = list(callable_fn(top=top)) if _accepts_top(callable_fn) else list(callable_fn())
            result = registry.ingest(provider, rows)
            result = DiscoveryRunResult(
                provider=provider,
                started_at=result.started_at,
                duration_ms=(time.monotonic() - started) * 1000.0,
                discovered=result.discovered,
                created=result.created,
                updated=result.updated,
                unchanged=result.unchanged,
                mapping_failures=result.mapping_failures,
            )
        except Exception as exc:  # noqa: BLE001 - provider isolation
            result = DiscoveryRunResult(
                provider=provider,
                started_at=time.time(),
                duration_ms=(time.monotonic() - started) * 1000.0,
                state="failed",
                reason=str(exc)[:200],
            )
        _DISCOVERY_COOLDOWNS[provider] = time.monotonic() + min_interval_seconds
        results[provider] = result
    return results


def _accepts_top(fn: Callable) -> bool:
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return "top" in sig.parameters or any(
        p.kind in (p.VAR_KEYWORD,) for p in sig.parameters.values()
    )


__all__ = [
    "DiscoveryRunResult",
    "DynamicInstrumentRegistry",
    "ProviderInstrument",
    "run_discovery",
]
