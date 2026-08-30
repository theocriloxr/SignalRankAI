# EVENT_CATALOGUE — SignalRankAI

Canonical source: `core/event_catalogue.py` (validated at runtime). Every core
event carries the full envelope from `core/durable_event_stream.py`
(`EventEnvelope`): event_id, event_type, schema_version, aggregate context,
tenant/organization/user/broker identity, signal/strategy/provider/venue,
correlation/causation/trace ids, idempotency_key, timestamps, producer
service/deployment, and a tamper-evident payload_hash.

## Core events by aggregate

| Aggregate | Events |
|---|---|
| Signal | SignalGenerated, SignalRejected, SignalReserved, SignalStored |
| Delivery | SignalDelivered, DeliveryFailed, DeliveryDeferred |
| Outcome | TP1Reached, TP2Reached, TP3Reached, StopReached, BreakevenReached, PartialExitCalculated, OutcomeFinalized, OutcomeCorrected |
| Paper position | EntryTriggered, EntryMissed, PaperPositionOpened, PaperPositionMarked, PaperPositionClosed |
| Order | OrderCreated, OrderReserved, OrderSubmitted, OrderAcknowledged, OrderPartiallyFilled, OrderFilled, OrderRejected, OrderCancelled |
| Position | PositionReconciled |
| Provider | ProviderQuarantined, ProviderRecovered |
| Payment/Subscription | PaymentConfirmed, PaymentFailed, SubscriptionActivated, EntitlementChanged |
| Model | ModelTrained, ModelPromoted, ModelRolledBack |
| System | KillSwitchActivated, KillSwitchReleased |

## Delivery semantics

* At-least-once transport (Redis Streams) + idempotent consumer inbox =
  exactly-once logical processing keyed on `idempotency_key` (default
  `event_id`).
* Ordering preserved per partition key (signal, user, account, order, position,
  ledger).
* Permanent failures route to the DLQ; retryable failures back off
  exponentially (`core/transactional_outbox.OutboxRelay`).
* Events are immutable once published; corrections are new events
  (`OutcomeCorrected`, ledger `CORRECTION` entries).
