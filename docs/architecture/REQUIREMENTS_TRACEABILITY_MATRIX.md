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


## Multi-user / multi-account execution addendum (2026-09-25)

Architecture companion:
`docs/architecture/MULTI_ACCOUNT_EXECUTION_SAFETY_2026-09-25.md`.

| ID | Requirement | Status | Implementation | Tests | Migration / docs | Verification evidence / related commits |
|---|---|---|---|---|---|---|
| SR-ID-010 | All broker-account object access is scoped by canonical `users.id + connection_id`; no BOLA/IDOR through normal policy, ledger, execution or evidence routes | UNIT_VERIFIED | `services/account_policies.py`, `services/broker_connections.py`, `services/trading_account_ledger.py`, `services/execution_evidence.py`, `web/platform_api.py` | `tests/test_broker_account_bola_idor.py` | addendum § identity/isolation | Clean-room targeted suite; commits `b3ce41e`, `ffb6460` |
| SR-ACCOUNT-010 | One canonical user may own multiple immutable broker connections with explicit PAPER/DEMO/LIVE_PERSONAL/PROP classification | UNIT_VERIFIED | `services/broker_connections.py`, `db/models.py` | `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` | `0041_broker_connection_registry`, `0043_account_execution_policy` | Conservative policy creation on every new connection; PR #71 |
| SR-ACCOUNT-011 | Every connected account owns a separately versioned execution/risk policy; material edits clear certification and disable execution | UNIT_VERIFIED | `core/account_policy.py`, `services/account_policies.py`, `web/platform_api.py` | `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` | `0043_account_execution_policy` | Commits `cfd4b30`, `3e53004`, `289bb96` |
| SR-EXEC-020 | Execution destination claims and prior-execution evidence are scoped to trading account, not only user+signal | UNIT_VERIFIED | `core/execution_claims.py`, `services/execution_evidence.py`, `services/broker_signal_router.py` | `tests/test_multi_account_prop_policy.py`, `tests/test_broker_account_bola_idor.py` | addendum § account selection | Account collisions removed; explicit account required when ambiguous |
| SR-EXEC-021 | Telegram manual execution uses short-lived opaque server-bound account-selection tokens; raw connection IDs are not trusted from callback payloads | UNIT_VERIFIED | `services/broker_account_selection.py`, `signalrank_telegram/bot.py`, callback registry | `tests/test_canonical_broker_entrypoints.py`, `tests/test_broker_account_bola_idor.py` | `requirements/callback_registry.yaml` | Policy-version/owner/signal binding verified in targeted suite |
| SR-EXEC-022 | MT5 and provider-neutral execution ledgers persist the canonical `connection_id` for new orders; ambiguous historical rows are never guessed | UNIT_VERIFIED | `services/mt5_signal_router.py`, `services/bybit_signal_router.py`, `db/models.py` | `tests/test_final_cross_channel_parity_20260925.py` | `0043_account_execution_policy` | 0043 backfills MT5 only where user+provider account maps uniquely |
| SR-PROP-010 | PROP rules are deterministic, versioned and configuration-driven rather than hard-coded to a named firm | UNIT_VERIFIED | `core/account_policy.py`, `services/account_policies.py` | `tests/test_multi_account_prop_policy.py` | architecture companion | Generic hard-rule engine commit `9f75536`; tests `b1e2e42` |
| SR-PROP-011 | PROP certification is an owner/admin-only operation bound to an exact policy version with certifier provenance | UNIT_VERIFIED | `services/account_policies.py`, `web/platform_api.py`, `db/models.py` | `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` | `0043_account_execution_policy` | Server-side authority + `admin_events`; commits `5ac80b...`/PR #71 |
| SR-RISK-010 | Per-account hard limits cover trade risk, daily/weekly/total loss, leverage, positions, spread/slippage, confidence/R:R, strategy/instrument and trading windows | UNIT_VERIFIED | `core/account_policy.py`, MT5/Bybit routers | `tests/test_multi_account_prop_policy.py` | `0043_account_execution_policy` | Deterministic reason codes; real accounts fail closed without verified loss baselines |
| SR-RECON-010 | Reconciliation is per account and material discrepancy/auth/disconnect states disable execution and freeze the affected policy | UNIT_VERIFIED | `services/account_policies.py`, `broker_reconciliation_state` | `tests/test_final_cross_channel_parity_20260925.py` | `0043_account_execution_policy` | Durable safety audit event; commit `f4d0eec` |
| SR-LEDGER-010 | Broker account financial/trade evidence is persisted in an append-only, account-owned, provider-idempotent canonical ledger | UNIT_VERIFIED | `services/trading_account_ledger.py`, `db/models.py` | `tests/test_trading_account_ledger.py`, `tests/test_broker_account_bola_idor.py`, parity tests | `0043_account_execution_policy`; immutable DB trigger | Commits `b486ddc`, `0585e11`; schema gate requires table |
| SR-LEDGER-011 | Bybit snapshots, orders, positions, realized P/L and provider-reported fees feed the canonical account ledger without inferred values | UNIT_VERIFIED | `services/bybit_signal_router.py`, `services/bybit_reconciler.py` | source/parity + ledger tests | architecture companion | Commits `11c105d`, `b5c7980`; live-provider certification remains a separate gate |
| SR-LEDGER-012 | MT4/MT5 account snapshots/orders plus exact MetaApi deal history feed canonical ledger; authoritative realized P/L, commission, swap and provider fees are ingested without symbol-only attribution | UNIT_VERIFIED | `services/mt5_signal_router.py`, `services/mt5_client.py`, `services/mt5_reconciler.py`, `worker/worker.py` | `tests/test_mt5_reconciliation_ledger.py`, `tests/test_v131_live_financial_activation.py`, parity tests | architecture companion | Commits `d9a2fdb`, `b80a846`, `b9d39ff`, `c400e4a`; live MetaApi provider certification remains a separate runtime gate |
| SR-AUDIT-010 | Policy edits, user safety freezes/unfreezes, operator PROP certification and reconciliation safety blocks are durably audited | UNIT_VERIFIED | `services/account_policies.py`, `AdminEvent` | `tests/test_final_cross_channel_parity_20260925.py` | architecture companion | Commit `f4d0eec`; no credentials stored in audit details |
| SR-PERF-010 | DEMO, LIVE_PERSONAL and PROP broker performance is composed per connection and not shown as a mixed user headline | UNIT_VERIFIED | `web/platform_api.py`, `web/platform_app/app.js` | `tests/test_final_cross_channel_parity_20260925.py` | architecture companion | Commits `56ab2cc`, `5a0ad98`; mixed aggregates retained only as labelled diagnostics |
| SR-WEB-010 | Web account UI exposes account policy, PROP rules, safety freeze, reconciliation and selected-account ledger evidence | UNIT_VERIFIED | `web/platform_app/index.html`, `app.js`, `platform_api.py` | parity tests | PWA cache rotated with each contract change | Policy/ledger UI commits `ff093aa`, `266a077` and later |
| SR-SCHEMA-010 | Runtime admission requires policy, reconciliation, canonical account ledger, decision provenance, and account-scoped execution columns at Alembic head 0043 | UNIT_VERIFIED | `scripts/assert_database_schema.py`, `scripts/staging_runtime_proof.py` | `tests/test_blueprint_certification_safety.py` | `0043_account_execution_policy` | Commits `32154e3`, `f4645f5` |
| SR-SCHEMA-011 | Shared staging DB is migrated to 0043 and passes post-migration runtime proof with live financial flags off | IN_PROGRESS | controlled migration/certification tooling | runtime certification suite | staging only; production untouched | **Not yet claimed**; gated on latest clean-room branch verification |
