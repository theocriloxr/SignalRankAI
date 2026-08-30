# RISK_REGISTER — SignalRankAI

Likelihood/impact: H/M/L. Mitigation column references the implementing module.

| ID | Risk | L | I | Mitigation |
|---|---|---|---|---|
| RR-001 | Live execution enabled without certification | M | H | `GLOBAL_EXECUTION_KILL_SWITCH`, `core/financial_activation.py` guarded gates, provider flags off |
| RR-002 | Duplicate financial effect from replay | M | H | idempotency keys, `IdempotentInbox`, ledger `DuplicateSourceEvent`, stream dedupe |
| RR-003 | Staging mutates production data/webhook | L | H | separate bots/tokens, staging fails closed on token, isolated Redis/DB per env |
| RR-004 | Secret leakage in logs | M | H | redaction tests, typed failure messages capped, no auth headers logged |
| RR-005 | Stale/unattributed quote drives a delivery | M | H | `data/provider_types.validate_quote_for_final_delivery` fail-closed |
| RR-006 | Outbox/queue growth unbounded | M | M | bounded streams, DLQ, relay budgets, backpressure |
| RR-007 | Single malformed record poisons a batch | M | M | per-item savepoints, per-item transactions, poison → DLQ |
| RR-008 | Provider outage cascades to all assets | M | M | circuit breakers, quarantine, capability-aware routing, no silent static fallback |
| RR-009 | Model promoted without gates | M | M | shadow/champion-gate contract (pending SR-ML-002/003) |
| RR-010 | Webhook ack p99 target missed under load | M | M | durable queue + immediate ack; SLO `webhook_ack_p99` + degradation |
| RR-011 | Credential/private-key compromise (brokers) | L | H | envelope encryption requirement, IP allowlisting, rotation (SR-SEC-004 pending) |
| RR-012 | 100k-user claim without load evidence | H | M | do not certify scale tiers; simulations labelled |
