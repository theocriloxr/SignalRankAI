"""Typed provider-failure taxonomy for the V2.0 provider architecture.

Providers must return typed failures instead of ambiguous ``None`` or opaque
strings so routing, circuit breakers, retry policy and operator tooling can
classify outcomes deterministically. This module is the single taxonomy used
across adapters; it deliberately matches the V2.0 programme section 8 list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProviderFailureReason(str, Enum):
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    AUTHENTICATION_FAILURE = "authentication_failure"
    PERMISSION_FAILURE = "permission_failure"
    RATE_LIMITED = "rate_limited"
    REGION_RESTRICTED = "region_restricted"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_MAINTENANCE = "provider_maintenance"
    INVALID_INSTRUMENT = "invalid_instrument"
    STALE_DATA = "stale_data"
    SEQUENCE_GAP = "sequence_gap"
    MALFORMED_PAYLOAD = "malformed_payload"
    INSUFFICIENT_HISTORY = "insufficient_history"
    MINIMUM_SIZE_VIOLATION = "minimum_size_violation"
    PRECISION_VIOLATION = "precision_violation"
    ORDER_REJECTED = "order_rejected"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    LICENSING_RESTRICTED = "licensing_restricted"
    MISSING_CREDENTIALS = "missing_credentials"
    MISSING_ACCOUNT = "missing_account"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    INVALID_SYMBOL_MAPPING = "invalid_symbol_mapping"
    ENTITLEMENT_FAILURE = "entitlement_failure"
    MARKET_CLOSED = "market_closed"
    TIMEOUT = "timeout"
    PROVIDER_OUTAGE = "provider_outage"
    INVALID_PAYLOAD = "invalid_payload"
    HTTP_403 = "http_403"
    HTTP_404 = "http_404"
    HTTP_429 = "http_429"
    UNKNOWN = "unknown"


#: Failures that must never be retried automatically.
PERMANENT_REASONS: frozenset[ProviderFailureReason] = frozenset({
    ProviderFailureReason.UNSUPPORTED_CAPABILITY,
    ProviderFailureReason.PERMISSION_FAILURE,
    ProviderFailureReason.INVALID_INSTRUMENT,
    ProviderFailureReason.UNSUPPORTED_SYMBOL,
    ProviderFailureReason.INVALID_SYMBOL_MAPPING,
    ProviderFailureReason.MALFORMED_PAYLOAD,
    ProviderFailureReason.INVALID_PAYLOAD,
    ProviderFailureReason.MINIMUM_SIZE_VIOLATION,
    ProviderFailureReason.PRECISION_VIOLATION,
    ProviderFailureReason.ORDER_REJECTED,
    ProviderFailureReason.RECONCILIATION_REQUIRED,
    ProviderFailureReason.LICENSING_RESTRICTED,
    ProviderFailureReason.MISSING_CREDENTIALS,
    ProviderFailureReason.HTTP_403,
    ProviderFailureReason.HTTP_404,
})

#: Failures that are safe and valuable to retry with backoff.
RETRYABLE_REASONS: frozenset[ProviderFailureReason] = frozenset({
    ProviderFailureReason.RATE_LIMITED,
    ProviderFailureReason.PROVIDER_UNAVAILABLE,
    ProviderFailureReason.PROVIDER_MAINTENANCE,
    ProviderFailureReason.TIMEOUT,
    ProviderFailureReason.PROVIDER_OUTAGE,
    ProviderFailureReason.STALE_DATA,
    ProviderFailureReason.SEQUENCE_GAP,
    ProviderFailureReason.HTTP_429,
})

#: HTTP status -> primary failure classification.
HTTP_STATUS_REASONS: Mapping[int, ProviderFailureReason] = {
    401: ProviderFailureReason.AUTHENTICATION_FAILURE,
    403: ProviderFailureReason.HTTP_403,
    404: ProviderFailureReason.HTTP_404,
    409: ProviderFailureReason.PERMISSION_FAILURE,
    429: ProviderFailureReason.HTTP_429,
    500: ProviderFailureReason.PROVIDER_UNAVAILABLE,
    502: ProviderFailureReason.PROVIDER_OUTAGE,
    503: ProviderFailureReason.PROVIDER_MAINTENANCE,
    504: ProviderFailureReason.TIMEOUT,
}


def classify_http_status(status: int) -> ProviderFailureReason:
    return HTTP_STATUS_REASONS.get(int(status), ProviderFailureReason.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider: str
    reason: ProviderFailureReason
    capability: str = "unknown"
    message: str = ""
    retryable: bool | None = None
    request_id: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.retryable is None:
            object.__setattr__(
                self,
                "retryable",
                self.reason in RETRYABLE_REASONS and self.reason not in PERMANENT_REASONS,
            )
        object.__setattr__(self, "provider", str(self.provider or "unknown").lower())

    @property
    def permanent(self) -> bool:
        return not bool(self.retryable)

    @property
    def is_retryable(self) -> bool:
        return bool(self.retryable)


def classify_failure(
    *,
    provider: str,
    capability: str = "unknown",
    reason: ProviderFailureReason = ProviderFailureReason.UNKNOWN,
    message: str = "",
    request_id: str | None = None,
    status_code: int | None = None,
    context: Mapping[str, Any] | None = None,
) -> ProviderFailure:
    """Build a typed failure, inferring the reason from an HTTP status when present."""
    effective_reason = reason
    if status_code is not None:
        effective_reason = classify_http_status(status_code)
    return ProviderFailure(
        provider=provider,
        reason=effective_reason,
        capability=capability,
        message=str(message)[:512],
        request_id=request_id,
        context=dict(context or {}),
    )


__all__ = [
    "HTTP_STATUS_REASONS",
    "PERMANENT_REASONS",
    "RETRYABLE_REASONS",
    "ProviderFailure",
    "ProviderFailureReason",
    "classify_failure",
    "classify_http_status",
]
