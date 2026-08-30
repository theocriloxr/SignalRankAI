"""Canonical event catalogue for the SignalRankAI event-driven platform.

Single source of truth for the core business event types defined in the V2.0
programme. Consumers and producers validate against this registry instead of
hard-coding event-type strings, so a typo in either direction fails fast at the
boundary rather than producing a silent, unattributable event.

This module is a pure registry: it performs no I/O and no secret handling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class AggregateType(str, Enum):
    SIGNAL = "signal"
    DELIVERY = "delivery"
    OUTCOME = "outcome"
    PAPER_POSITION = "paper_position"
    ORDER = "order"
    POSITION = "position"
    PROVIDER = "provider"
    SUBSCRIPTION = "subscription"
    PAYMENT = "payment"
    ENTITLEMENT = "entitlement"
    MODEL = "model"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class EventSpec:
    event_type: str
    aggregate: AggregateType
    producer: str
    description: str
    idempotency_key: str = "event_id"


#: Core event catalogue from the V2.0 programme (section 6.1).
CORE_EVENTS: Mapping[str, EventSpec] = {
    "SignalGenerated": EventSpec("SignalGenerated", AggregateType.SIGNAL, "engine", "A strategy candidate passed base qualification."),
    "SignalRejected": EventSpec("SignalRejected", AggregateType.SIGNAL, "engine", "A strategy candidate was rejected with a stage and reason."),
    "SignalReserved": EventSpec("SignalReserved", AggregateType.SIGNAL, "engine", "A canonical signal reserved for delivery."),
    "SignalStored": EventSpec("SignalStored", AggregateType.SIGNAL, "engine", "A canonical signal was persisted."),
    "SignalDelivered": EventSpec("SignalDelivered", AggregateType.DELIVERY, "delivery", "A signal was delivered to a recipient."),
    "DeliveryFailed": EventSpec("DeliveryFailed", AggregateType.DELIVERY, "delivery", "A delivery attempt failed."),
    "DeliveryDeferred": EventSpec("DeliveryDeferred", AggregateType.DELIVERY, "delivery", "A delivery was deferred (budget, backoff or quiet hours)."),
    "EntryTriggered": EventSpec("EntryTriggered", AggregateType.PAPER_POSITION, "worker", "A paper position entry was triggered."),
    "EntryMissed": EventSpec("EntryMissed", AggregateType.PAPER_POSITION, "worker", "A paper entry window closed without execution."),
    "TP1Reached": EventSpec("TP1Reached", AggregateType.OUTCOME, "worker", "First take-profit milestone reached."),
    "TP2Reached": EventSpec("TP2Reached", AggregateType.OUTCOME, "worker", "Second take-profit milestone reached."),
    "TP3Reached": EventSpec("TP3Reached", AggregateType.OUTCOME, "worker", "Third take-profit milestone reached."),
    "StopReached": EventSpec("StopReached", AggregateType.OUTCOME, "worker", "Stop loss was hit."),
    "BreakevenReached": EventSpec("BreakevenReached", AggregateType.OUTCOME, "worker", "Position moved to breakeven."),
    "PartialExitCalculated": EventSpec("PartialExitCalculated", AggregateType.OUTCOME, "worker", "A partial exit was calculated."),
    "OutcomeFinalized": EventSpec("OutcomeFinalized", AggregateType.OUTCOME, "worker", "A terminal outcome was finalized."),
    "OutcomeCorrected": EventSpec("OutcomeCorrected", AggregateType.OUTCOME, "worker", "A human or system correction was recorded."),
    "PaperPositionOpened": EventSpec("PaperPositionOpened", AggregateType.PAPER_POSITION, "paper", "A paper position was opened."),
    "PaperPositionMarked": EventSpec("PaperPositionMarked", AggregateType.PAPER_POSITION, "paper", "A paper position was marked to market."),
    "PaperPositionClosed": EventSpec("PaperPositionClosed", AggregateType.PAPER_POSITION, "paper", "A paper position was closed."),
    "OrderCreated": EventSpec("OrderCreated", AggregateType.ORDER, "execution", "An order was created."),
    "OrderReserved": EventSpec("OrderReserved", AggregateType.ORDER, "execution", "Risk and cash reservation succeeded."),
    "OrderSubmitted": EventSpec("OrderSubmitted", AggregateType.ORDER, "execution", "An order was submitted to a venue."),
    "OrderAcknowledged": EventSpec("OrderAcknowledged", AggregateType.ORDER, "execution", "A venue acknowledged the order."),
    "OrderPartiallyFilled": EventSpec("OrderPartiallyFilled", AggregateType.ORDER, "execution", "An order was partially filled."),
    "OrderFilled": EventSpec("OrderFilled", AggregateType.ORDER, "execution", "An order was fully filled."),
    "OrderRejected": EventSpec("OrderRejected", AggregateType.ORDER, "execution", "A venue rejected the order."),
    "OrderCancelled": EventSpec("OrderCancelled", AggregateType.ORDER, "execution", "An order was cancelled."),
    "PositionReconciled": EventSpec("PositionReconciled", AggregateType.POSITION, "execution", "A position was reconciled against the venue."),
    "ProviderQuarantined": EventSpec("ProviderQuarantined", AggregateType.PROVIDER, "market_data", "A provider was quarantined by the circuit breaker."),
    "ProviderRecovered": EventSpec("ProviderRecovered", AggregateType.PROVIDER, "market_data", "A quarantined provider recovered."),
    "SubscriptionActivated": EventSpec("SubscriptionActivated", AggregateType.SUBSCRIPTION, "payments", "A verified payment activated a subscription."),
    "PaymentConfirmed": EventSpec("PaymentConfirmed", AggregateType.PAYMENT, "payments", "A payment was verified server-side."),
    "PaymentFailed": EventSpec("PaymentFailed", AggregateType.PAYMENT, "payments", "A payment failed verification."),
    "EntitlementChanged": EventSpec("EntitlementChanged", AggregateType.ENTITLEMENT, "payments", "A user entitlement changed."),
    "ModelTrained": EventSpec("ModelTrained", AggregateType.MODEL, "ml", "A model finished training."),
    "ModelPromoted": EventSpec("ModelPromoted", AggregateType.MODEL, "ml", "A champion model was promoted after gates passed."),
    "ModelRolledBack": EventSpec("ModelRolledBack", AggregateType.MODEL, "ml", "A model was automatically rolled back."),
    "KillSwitchActivated": EventSpec("KillSwitchActivated", AggregateType.SYSTEM, "ops", "An execution or global kill switch was activated."),
    "KillSwitchReleased": EventSpec("KillSwitchReleased", AggregateType.SYSTEM, "ops", "An execution or global kill switch was released."),
}


def validate_event_type(event_type: str) -> str:
    """Return the canonical event type or raise ValueError."""
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type is required")
    spec = CORE_EVENTS.get(event_type)
    if spec is None:
        raise ValueError(f"unknown_event_type:{event_type}")
    return event_type


def event_spec_for(event_type: str) -> EventSpec | None:
    return CORE_EVENTS.get(event_type)


def all_event_types() -> tuple[str, ...]:
    return tuple(CORE_EVENTS.keys())


def events_for_aggregate(aggregate: AggregateType) -> tuple[str, ...]:
    return tuple(spec.event_type for spec in CORE_EVENTS.values() if spec.aggregate is aggregate)


__all__ = [
    "AggregateType",
    "CORE_EVENTS",
    "EventSpec",
    "all_event_types",
    "event_spec_for",
    "events_for_aggregate",
    "validate_event_type",
]
