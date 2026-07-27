"""Typed market-quote contracts used at consequential delivery boundaries.

Analysis code may still consume cached floats through compatibility wrappers.
Final signal delivery must instead carry a :class:`LivePriceQuote` through the
trust policy below so provider time, quote kind, health, and market state are
never inferred from the local fetch completion time.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class QuoteKind(str, Enum):
    TRADE = "trade"
    BID_ASK = "bid_ask"
    TICKER = "ticker"
    PREVIOUS_CLOSE = "previous_close"
    DB_TICK = "db_tick"


class ProviderHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class BreakerState(str, Enum):
    CLOSED = "closed"
    HALF_OPEN = "half_open"
    OPEN = "open"


@dataclass(frozen=True, slots=True)
class LivePriceQuote:
    """One provider observation with source-time and provenance metadata.

    The first five fields retain the original constructor contract. New fields
    default conservatively: a legacy quote without source time or provider
    health remains usable by analysis callers but is rejected at final send.
    """

    symbol: str
    price: float
    provider: str
    fetched_at: float
    latency_ms: int
    confidence: float = 1.0
    is_stale: bool = False
    stale_reason: str | None = None
    provider_symbol: str | None = None
    asset_class: str = "unknown"
    bid: float | None = None
    ask: float | None = None
    source_timestamp: float | None = None
    received_at: float | None = None
    completed_at: float | None = None
    session: str = "unknown"
    market_status: str = "unknown"
    provider_health: str = ProviderHealthState.UNKNOWN.value
    breaker_state: str = BreakerState.CLOSED.value
    confidence_reasons: tuple[str, ...] = ()
    quote_kind: str = QuoteKind.TICKER.value
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cross_provider_deviation_pct: float | None = None
    untrusted_reason: str | None = None

    def __post_init__(self) -> None:
        canonical = str(self.symbol or "").upper().strip()
        object.__setattr__(self, "symbol", canonical)
        object.__setattr__(self, "provider", str(self.provider or "").lower().strip())
        object.__setattr__(
            self,
            "provider_symbol",
            str(self.provider_symbol or canonical).upper().strip(),
        )
        object.__setattr__(self, "asset_class", normalize_asset_class(self.asset_class))
        object.__setattr__(self, "received_at", float(self.received_at or self.fetched_at))
        object.__setattr__(self, "completed_at", float(self.completed_at or self.fetched_at))
        object.__setattr__(self, "confidence_reasons", tuple(self.confidence_reasons or ()))

    @property
    def canonical_symbol(self) -> str:
        return self.symbol

    @property
    def mid(self) -> float:
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (float(self.bid) + float(self.ask)) / 2.0
        return float(self.price)

    def source_age_seconds(self, now: float | None = None) -> float | None:
        if self.source_timestamp is None:
            return None
        return float(now if now is not None else time.time()) - float(self.source_timestamp)


@dataclass(frozen=True, slots=True)
class LivePriceFailure:
    """Typed provider failure; callers no longer have to interpret ``None``."""

    symbol: str
    provider: str
    reason: str
    retryable: bool = True
    provider_symbol: str | None = None
    asset_class: str = "unknown"
    breaker_state: str = BreakerState.CLOSED.value
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True, slots=True)
class FinalQuotePolicy:
    """Versioned, pure policy for final-delivery quote admission."""

    version: str = "phase4-pass1-v1"
    max_source_age_seconds: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType(
            {
                "crypto": 10.0,
                "fx": 15.0,
                "commodity": 15.0,
                "stock": 30.0,
                "index": 30.0,
            }
        )
    )
    min_confidence: float = 0.75
    max_cross_provider_deviation_pct: float = 1.0
    max_future_clock_skew_seconds: float = 5.0
    allowed_quote_kinds: tuple[str, ...] = (
        QuoteKind.TRADE.value,
        QuoteKind.BID_ASK.value,
        QuoteKind.TICKER.value,
        QuoteKind.DB_TICK.value,
    )


@dataclass(frozen=True, slots=True)
class QuoteTrustDecision:
    ok: bool
    reason: str
    state: str
    policy_version: str
    source_age_seconds: float | None = None
    max_source_age_seconds: float | None = None
    checks: tuple[str, ...] = ()


def normalize_asset_class(asset_class: str | None) -> str:
    value = str(asset_class or "unknown").strip().lower()
    aliases = {"forex": "fx", "equity": "stock", "indices": "index"}
    return aliases.get(value, value)


def _finite_positive(value: float | None) -> bool:
    try:
        return value is not None and math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def validate_quote_for_final_delivery(
    quote: LivePriceQuote | None,
    *,
    market_open: bool | None,
    market_reason: str | None = None,
    now: float | None = None,
    policy: FinalQuotePolicy | None = None,
) -> QuoteTrustDecision:
    """Fail closed unless a quote is live, attributable, fresh, and tradeable."""

    policy = policy or FinalQuotePolicy()
    if quote is None:
        return QuoteTrustDecision(
            False,
            "quote_unavailable",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
        )

    checks: list[str] = []
    if not quote.symbol or not quote.provider or not _finite_positive(quote.price):
        return QuoteTrustDecision(
            False,
            "quote_identity_or_price_invalid",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
        )
    checks.append("identity_and_price")

    quote_kind = str(quote.quote_kind or "").lower()
    if quote_kind == QuoteKind.PREVIOUS_CLOSE.value:
        return QuoteTrustDecision(
            False,
            "analysis_only_previous_close",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
        )
    if quote_kind not in policy.allowed_quote_kinds:
        return QuoteTrustDecision(
            False,
            f"quote_kind_not_allowed:{quote_kind or 'missing'}",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
        )
    checks.append("quote_kind")

    if quote.source_timestamp is None:
        reason = "db_tick_missing_source_timestamp" if quote_kind == QuoteKind.DB_TICK.value else "missing_source_timestamp"
        return QuoteTrustDecision(False, reason, "BLOCKED_PROVIDER_UNTRUSTED", policy.version)

    asset_class = normalize_asset_class(quote.asset_class)
    max_age = policy.max_source_age_seconds.get(asset_class)
    if max_age is None:
        return QuoteTrustDecision(
            False,
            f"unsupported_asset_class:{asset_class}",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
        )
    source_age = quote.source_age_seconds(now=now)
    if source_age is None:
        return QuoteTrustDecision(False, "missing_source_timestamp", "BLOCKED_PROVIDER_UNTRUSTED", policy.version)
    if source_age < -policy.max_future_clock_skew_seconds:
        return QuoteTrustDecision(
            False,
            f"source_clock_in_future:{source_age:.3f}s",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
            source_age,
            max_age,
        )
    if source_age > max_age or quote.is_stale:
        stale_reason = quote.stale_reason or f"source_age_exceeded:{source_age:.3f}s>{max_age:.3f}s"
        return QuoteTrustDecision(
            False,
            stale_reason,
            "BLOCKED_STALE",
            policy.version,
            source_age,
            max_age,
        )
    checks.append("source_age")

    health = str(quote.provider_health or "unknown").lower()
    breaker = str(quote.breaker_state or "closed").lower()
    if quote.untrusted_reason:
        return QuoteTrustDecision(False, quote.untrusted_reason, "BLOCKED_PROVIDER_UNTRUSTED", policy.version, source_age, max_age)
    if health != ProviderHealthState.HEALTHY.value:
        return QuoteTrustDecision(False, f"provider_health:{health}", "BLOCKED_PROVIDER_UNTRUSTED", policy.version, source_age, max_age)
    if breaker != BreakerState.CLOSED.value:
        return QuoteTrustDecision(False, f"provider_breaker:{breaker}", "BLOCKED_PROVIDER_UNTRUSTED", policy.version, source_age, max_age)
    if not math.isfinite(float(quote.confidence)) or float(quote.confidence) < policy.min_confidence:
        return QuoteTrustDecision(False, f"confidence_too_low:{quote.confidence}", "BLOCKED_PROVIDER_UNTRUSTED", policy.version, source_age, max_age)
    if (
        quote.cross_provider_deviation_pct is not None
        and float(quote.cross_provider_deviation_pct) > policy.max_cross_provider_deviation_pct
    ):
        return QuoteTrustDecision(
            False,
            f"cross_provider_deviation:{quote.cross_provider_deviation_pct}",
            "BLOCKED_PROVIDER_UNTRUSTED",
            policy.version,
            source_age,
            max_age,
        )
    checks.append("provider_trust")

    if market_open is not True:
        return QuoteTrustDecision(
            False,
            market_reason or "market_state_unknown",
            "BLOCKED_MARKET_CLOSED",
            policy.version,
            source_age,
            max_age,
            tuple(checks),
        )
    checks.append("market_open")

    return QuoteTrustDecision(
        True,
        "trusted_live_quote",
        "LIVE_QUOTE_TRUST_PASSED",
        policy.version,
        source_age,
        max_age,
        tuple(checks),
    )


__all__ = [
    "BreakerState",
    "FinalQuotePolicy",
    "LivePriceFailure",
    "LivePriceQuote",
    "ProviderHealthState",
    "QuoteKind",
    "QuoteTrustDecision",
    "normalize_asset_class",
    "validate_quote_for_final_delivery",
]
