"""Validate shared opportunity state before spending work on each recipient."""
from __future__ import annotations

from typing import Any

from data.provider_types import LivePriceQuote
from engine.delivery_freshness import DeliveryFreshnessResult, validate_delivery_freshness


async def prefilter_delivery_candidate(
    signal: dict[str, Any], quote: LivePriceQuote | None,
) -> DeliveryFreshnessResult:
    # Prefetch has already made the bounded provider call. An unavailable quote
    # must not trigger an unbounded series of per-signal network retries here.
    if not isinstance(quote, LivePriceQuote):
        return DeliveryFreshnessResult(False, "prefilter_quote_unavailable", state="BLOCKED_PROVIDER_UNTRUSTED")
    if quote.canonical_symbol != str(signal.get("asset") or signal.get("symbol") or "").strip().upper():
        return DeliveryFreshnessResult(False, "prefilter_quote_symbol_mismatch", state="BLOCKED_PROVIDER_UNTRUSTED")
    try:
        return await validate_delivery_freshness(signal, live_quote=quote, final_send=True)
    except Exception as exc:
        return DeliveryFreshnessResult(
            False, f"prefilter_validation_error:{type(exc).__name__}", state="BLOCKED_PROVIDER_UNTRUSTED",
        )


def analytical_age_expired(reason: str) -> bool:
    """Provider outages, queue expiry and missed entry do not rewrite analysis."""
    return str(reason).startswith(("age_exceeded:", "opportunity_decayed:"))
