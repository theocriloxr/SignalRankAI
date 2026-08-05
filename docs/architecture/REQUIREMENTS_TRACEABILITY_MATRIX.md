# REQUIREMENTS_TRACEABILITY_MATRIX — SignalRankAI V2.0

Traceability IDs assigned per programme area. Statuses restricted to the
programme vocabulary. `UNIT_VERIFIED` means deterministic unit coverage in the
current checkout; `BLOCKED_EXTERNAL` means the capability needs credentials,
infrastructure or a legal/licensing decision.

## Baseline integrity

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-BASE-001 | Outcome persistence independent of notification fan-out | UNIT_VERIFIED | `services/outcome_reconciliation.py`, outbox repair | `test_v1369_outcome_delivery_recovery.py` | — |
| SR-BASE-002 | Central `_env_bool` helpers | UNIT_VERIFIED | `core/env.py` | suite-wide | — |
| SR-BASE-003 | Performance reconciliation per-user failure isolation | UNIT_VERIFIED | `services/performance_ledger.py` | `test_v1368_performance_scale_hotfix.py` | — |
| SR-BASE-004 | Terminal outcome ordering (tp1→tp2/tp3 progression) | UNIT_VERIFIED | `core/outcome_ordering.py` | outcome tests | — |

## Events (§6)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-EVENT-001 | Full envelope identity (aggregate/trace/deployment/payload hash) | UNIT_VERIFIED | `core/durable_event_stream.py` | `test_v20_event_platform.py` | `DURABLE_EVENT_STREAM_ENABLED` |
| SR-EVENT-002 | Canonical event catalogue + validation | UNIT_VERIFIED | `core/event_catalogue.py` | `test_v20_event_platform.py` | — |
| SR-EVENT-003 | Transactional outbox contract | UNIT_VERIFIED | `core/transactional_outbox.py` | `test_v20_event_platform.py` | — |
| SR-EVENT-004 | Idempotent consumer inbox (exactly-once logical) | UNIT_VERIFIED | `core/transactional_outbox.py` | `test_v20_event_platform.py` | — |
| SR-EVENT-005 | Bounded relay, backoff, dead-letter | UNIT_VERIFIED | `core/transactional_outbox.py` | `test_v20_event_platform.py` | — |
| SR-EVENT-006 | Partitioned transport + consumer groups + reclaim | INTEGRATION_VERIFIED (code) | `core/durable_event_stream.py`, `core/redis_streams.py` | connector-level tests | `DURABLE_EVENT_STREAM_ENABLED` |

## Providers (§8–§10)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-PROVIDER-001 | Typed failure taxonomy (§8 list) | UNIT_VERIFIED | `data/provider_failures.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-002 | HTTP status classification + retry policy | UNIT_VERIFIED | `data/provider_failures.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-003 | Capability manifest + certification states | UNIT_VERIFIED | `data/provider_contracts.py` | `test_provider_catalog_and_certification.py` | — |
| SR-PROVIDER-004 | Canonical instrument model (tick/minimums/aliases/status) | UNIT_VERIFIED | `data/canonical_instruments.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-005 | Quote trust policy (freshness, provenance, no candle-as-quote) | UNIT_VERIFIED | `data/provider_types.py` | provider tests | — |
| SR-PROVIDER-006 | Circuit breakers + quarantine | UNIT_VERIFIED | `core/circuit_breaker.py` | `test_provider_registry_fail_closed.py` | — |
| SR-PROVIDER-007 | Venue adapters (Binance/Bybit/OKX/Hyperliquid/OANDA/IBKR/Alpaca/Tradier/…) | BLOCKED_EXTERNAL | declared interfaces only | — | provider flags off |

## Risk and ledger (§12–§13)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-RISK-001 | Portfolio risk authority (exposure + breakers) | UNIT_VERIFIED | `core/risk_authority.py` | `test_v20_risk_authority.py` | — |
| SR-RISK-002 | Kill-switch gate on every admission | UNIT_VERIFIED | `core/risk_authority.py`, `core/financial_activation.py` | risk + activation tests | `GLOBAL_EXECUTION_KILL_SWITCH` |
| SR-RISK-003 | Append-only financial ledger | UNIT_VERIFIED | `core/financial_ledger.py` | `test_v20_financial_ledger.py` | — |
| SR-RISK-004 | Compensating corrections + double entry + imbalance detection | UNIT_VERIFIED | `core/financial_ledger.py` | `test_v20_financial_ledger.py` | — |

## ML (§16)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-ML-001 | Calibration rules (no uncalibrated score as probability) | UNIT_VERIFIED | `engine/ml_weighting.py` + telemetry | ML tests | — |
| SR-ML-002 | Champion/challenger + shadow promotion + rollback | IMPLEMENTED_UNTESTED | adaptive runtime | — | `ADAPTIVE_LEARNING_ENABLED` |
| SR-ML-003 | Full model registry / lineage / leakage gates | NOT_STARTED | — | — | — |

## Security (§21)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-SEC-001 | Secret redaction in logs | UNIT_VERIFIED | prior repair pass; `core/security.py` | secret-leak tests | — |
| SR-SEC-002 | Signed webhook verification from raw body | UNIT_VERIFIED | `payments/paystack_events.py` | webhook tests | — |
| SR-SEC-003 | Threat model documented | IN_PROGRESS | `docs/security/THREAT_MODEL.md` | — | — |
| SR-SEC-004 | Envelope encryption for broker credentials | NOT_STARTED | — | — | `BROKER_CREDENTIAL_ENCRYPTION` |

## Scale (§27) and observability (§25)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-SCALE-001 | SLO registry + error budgets + degradation | UNIT_VERIFIED | `core/slo_registry.py` | `test_v20_slo_registry.py` | — |
| SR-SCALE-002 | Bounded queues / backpressure / DLQ | UNIT_VERIFIED | `core/redis_streams.py`, `core/transactional_outbox.py` | queue tests | — |
| SR-SCALE-003 | 100k-user load certification | BLOCKED_EXTERNAL | load scripts required | — | — |

## Notifications (§23) and trading (§14–§15, §18)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-NOTIF-001 | Notification outbox repair bounded | UNIT_VERIFIED | outcome reconciliation | v1.3.6.9 tests | — |
| SR-NOTIF-002 | Dedicated fan-out reservation service | IMPLEMENTED_UNTESTED | outbox + stream layers | — | — |
| SR-ORDER-001 | Canonical order/position state machines | IMPLEMENTED_UNTESTED | execution claims + trade tracker | — | `REAL_EXECUTION_ENABLED=0` |
| SR-ORDER-002 | Copy trading / marketplace / bots / smart terminal | BLOCKED_EXTERNAL | declared in roadmap | — | flags off |
