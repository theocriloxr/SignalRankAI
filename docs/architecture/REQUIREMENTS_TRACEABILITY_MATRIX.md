# REQUIREMENTS_TRACEABILITY_MATRIX — SignalRankAI V2.0

Traceability IDs assigned per programme area. Statuses restricted to the
programme vocabulary. `UNIT_VERIFIED` means deterministic repository coverage;
`INTEGRATION_VERIFIED` means the contract also has real staging/runtime evidence;
`BLOCKED_EXTERNAL` means the remaining proof requires credentials, representative
infrastructure, elapsed runtime, provider entitlements, or a legal/licensing decision.

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
| SR-EVENT-006 | Partitioned transport + consumer groups + reclaim | UNIT_VERIFIED | `core/durable_event_stream.py`, `core/redis_streams.py` | connector-level event/stream tests | `DURABLE_EVENT_STREAM_ENABLED` |

## Providers (§8–§10)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-PROVIDER-001 | Typed failure taxonomy (§8 list) | UNIT_VERIFIED | `data/provider_failures.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-002 | HTTP status classification + retry policy | UNIT_VERIFIED | `data/provider_failures.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-003 | Capability manifest + certification states | UNIT_VERIFIED | `data/provider_contracts.py` | `test_provider_catalog_and_certification.py` | — |
| SR-PROVIDER-004 | Canonical instrument model (tick/minimums/aliases/status) | UNIT_VERIFIED | `data/canonical_instruments.py` | `test_v20_provider_layer.py` | — |
| SR-PROVIDER-005 | Quote trust policy (freshness, provenance, no candle-as-quote) | UNIT_VERIFIED | `data/provider_types.py` | provider tests | — |
| SR-PROVIDER-006 | Circuit breakers + quarantine | UNIT_VERIFIED | `core/circuit_breaker.py` | `test_provider_registry_fail_closed.py` | — |
| SR-PROVIDER-007 | Declared venue/provider capabilities are independently live/sandbox certified before being claimed production-ready | BLOCKED_EXTERNAL | provider catalogue/adapters, `scripts/certify_providers.py`, `scripts/deployment_diagnostics.py` | `tests/test_provider_catalog_and_certification.py`, `tests/test_provider_certification_entrypoint.py` | External credentials/plans/entitlements and live evidence required; uncertified provider flags remain off |

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
| SR-ML-002 | Champion/challenger + shadow promotion + rollback | UNIT_VERIFIED | `ml/train_model.py`, `engine/ml.py`, durable model artifact store | `tests/test_ml_champion_challenger_governance.py`, `tests/test_ml_registry.py`, `tests/test_ml_durable_artifact_sync.py` | `ADAPTIVE_LEARNING_ENABLED` |
| SR-ML-003 | Full model registry / dataset-run-parent lineage / leakage gates | UNIT_VERIFIED | `ml/model_registry.py`, `ml/train_model.py`, adaptive dataset/WFO contracts | `tests/test_ml_registry.py`, `tests/test_adaptive_dataset_and_wfo.py`, ML schema/leakage tests | — |

## Security (§21)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-SEC-001 | Secret redaction in logs | UNIT_VERIFIED | prior repair pass; `core/security.py` | secret-leak tests | — |
| SR-SEC-002 | Signed webhook verification from raw body | UNIT_VERIFIED | `payments/paystack_events.py` | webhook tests | — |
| SR-SEC-003 | Threat model documented against the deployed 0045 architecture and residual-risk boundary | INTEGRATION_VERIFIED | `docs/security/THREAT_MODEL.md` | release/security contract review + staging 0045 evidence | — |
| SR-SEC-004 | Versioned, account-bound envelope encryption and key rotation for broker credentials | INTEGRATION_VERIFIED | `services/broker_credentials.py`, canonical broker connection writer, `0044_broker_credential_envelope` | `test_broker_credential_envelope.py` | `BROKER_CREDENTIAL_KEYRING_JSON`, `BROKER_CREDENTIAL_ACTIVE_KEY_ID` |
| SR-SEC-005 | Deterministic dependency SBOM and release provenance bind the locked graph, Dockerfile, current release contract, exact commit/branch and Alembic head | UNIT_VERIFIED | `scripts/generate_release_provenance.py`, `requirements.lock` | `tests/test_release_provenance.py`; clean-room provenance self-check | external signing key remains separate |

## Scale (§27) and observability (§25)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-SCALE-001 | SLO registry + error budgets + degradation | UNIT_VERIFIED | `core/slo_registry.py` | `test_v20_slo_registry.py` | — |
| SR-SCALE-002 | Bounded queues / backpressure / DLQ | UNIT_VERIFIED | `core/redis_streams.py`, `core/transactional_outbox.py` | queue tests | — |
| SR-SCALE-003 | 100k-user / 20k-concurrent representative infrastructure certification | BLOCKED_EXTERNAL | `scripts/load_certification.py`, `requirements/scale_profiles.yaml`, SLO/queue/role architecture | `tests/test_load_certification.py` | Harness complete; representative distributed infrastructure run + runtime metrics/soak evidence required before any capacity claim |

## Notifications (§23) and trading (§14–§15, §18)

| ID | Requirement | Status | Source | Tests | Flag |
|---|---|---|---|---|---|
| SR-NOTIF-001 | Notification outbox repair bounded | UNIT_VERIFIED | outcome reconciliation | v1.3.6.9 tests | — |
| SR-NOTIF-002 | Dedicated fan-out reservation/idempotency boundary | UNIT_VERIFIED | `db/pg_features.py`, `delivery/service.py`, outbox/receipt layers | `tests/test_phase4_pass3_delivery_reliability.py`, `tests/test_delivery_fanout_planner.py` | — |
| SR-ORDER-001 | Canonical monotonic order/execution state machine with one position-state projection | UNIT_VERIFIED | `core/execution_state_machine.py`, MT5/Bybit routers and reconcilers | `tests/test_execution_state_machine.py`, `tests/test_canonical_broker_entrypoints.py` | `REAL_EXECUTION_ENABLED=0` |
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
| SR-SCHEMA-011 | Shared staging DB is migrated to 0043 and passes post-migration runtime proof with live financial flags off | INTEGRATION_VERIFIED | controlled migration/certification tooling | runtime certification suite | staging only; production untouched | Migration deployment `ec5be43c-0658-4398-93fc-50917b387158`: 0042→0043, schema gate PASS, runtime proof PASS, zero blockers, kill switch on and live-financial flags off |

| SR-RUNTIME-010 | Frontdoor, engine, delivery/worker and analytics roles can prove exact release identity and 0043 schema compatibility without starting business loops | INTEGRATION_VERIFIED | `start.sh`, `scripts/quiescent_role.py`, `runtime/roles.py` | `tests/test_quiescent_role_certification.py`; clean-room targeted suite | staging-only quiescent certification | Analytics `284ed63b-0716-48e4-9498-41dc270c0e6f`, engine `a67a3f14-5944-4e27-b8c3-245c1a3bd96b`, worker `d4a490dc-ce9f-4e30-9fae-172ac94cbe3f`, frontdoor `a562a609-b533-46e9-aa2b-bbffcc5bbdc4`; all release/schema gates PASS, business loops disabled, production untouched |
| SR-RUNTIME-011 | Long-lived staging analytics, delivery, engine and frontdoor roles run against the certified 0043 schema with explicit non-overlapping ownership | INTEGRATION_VERIFIED | `runtime/roles.py`, `runtime/analytics.py`, `runtime/delivery.py`, `runtime/engine.py`, `runtime/frontdoor.py`, `start.sh` | clean-room + locked Docker build gate + live Railway admission | `docs/evidence/STAGING_0043_ROLE_CERTIFICATION_20260925.md` | Analytics `af352868-be5d-4012-90fc-ca56dc06252f`; delivery `0e82f4b8-d4d9-4bf7-bcfe-a87e3a8be044`; engine `de79e783-f33a-4cc2-8871-b6f3bc60c470`; frontdoor `a3d77cb6-5933-4634-83be-56b6b6426702`; all on 0043 + certified dependency lock, release/schema gates PASS |
| SR-MARKET-010 | Engine supports crypto, FX, equities, indices and commodities and applies market-session calendars before cycle admission | INTEGRATION_VERIFIED | `engine/core.py`, `data/class_universe.py`, `data/database_universe.py`, market/session classifiers | provider-discovery/build tests + live staging engine evidence | staging engine deployment | Active engine: crypto usable=250, FX=16, equities=23, indices=5, commodities=4; non-crypto zero-open counts during first post-cutover cycle were explicitly caused by Friday/session closures, not crypto-only filtering |
| SR-WEB-011 | Public staging frontdoor serves HTTP + Telegram without owning engine/worker loops and exposes a healthy external dashboard | INTEGRATION_VERIFIED | `runtime/frontdoor.py`, `railway_main.py`, `start.sh` | locked build gate + live /healthz + external browser check | staging frontdoor deployment | Deployment `a3d77cb6-5933-4634-83be-56b6b6426702`: Alembic 0043/schema PASS, frontdoor DB admission active, Uvicorn 8080, /healthz=200, Telegram webhook pending=0 |
| SR-RELEASE-010 | Staging rollout markers cannot automatically deploy production and role-specific watch paths prevent cross-role restart fan-out | INTEGRATION_VERIFIED | Railway watch-pattern rollout contract + release-source gate | live deployment history | staging rollout evidence | Frontdoor/engine/delivery/analytics production marker deployments were SKIPPED; staging frontdoor marker rebuilt only frontdoor while other staging roles skipped; production database untouched |
| SR-RELEASE-011 | Runtime dependency graph is reproducible and staging roles use the certified lock rather than floating direct dependency ranges | INTEGRATION_VERIFIED | `requirements.lock`, Dockerfile `pip install --no-deps` + `pip check` | locked build gate; dependency lock tests | staging role deployments | Analytics `3a1e072`, delivery `3b5ff87`, engine `b6bfdec`, frontdoor `4e6575d`; locked images passed repository build/readiness gates |
| SR-SCALE-010 | Adaptive candle persistence cannot monopolize the tiny engine DB pool under foreground pressure | INTEGRATION_VERIFIED | `engine/adaptive/candle_store.py` | `test_adaptive_and_shadow_writes_are_durable_background_work`, `test_adaptive_candle_pressure_requeues_full_batch` | engine runtime evidence | Engine `de79e783-f33a-4cc2-8871-b6f3bc60c470`: foreground-reserve deferrals were immediate, full batches requeued, bounded 2-snapshot/400-candle write succeeded, 5/5 candle fetch remained responsive, no warning/error severity |


| SR-SEC-010 | Broker credential ciphertext is bound to canonical user + connection + provider + connector + revision and rejects context replay | INTEGRATION_VERIFIED | `services/broker_credentials.py` | `tests/test_broker_credential_envelope.py` | `0044_broker_credential_envelope` | Clean-room + long-lived staging 0045 role admission |
| SR-SEC-011 | Broker key rotation supports previous-key reads/current-key writes, disables execution on rotation and records non-secret audit provenance | UNIT_VERIFIED | `services/broker_credentials.py`, `AdminEvent` | `tests/test_broker_credential_envelope.py` | credential keyring contract | Missing/unknown keys fail closed |
| SR-SEC-012 | Duplicate MT5 password persistence is retired after canonical credential-envelope migration | INTEGRATION_VERIFIED | `0045_mt5_credential_retirement`, `services/mt5_client.py` | `tests/test_broker_credential_envelope.py`, inventory tests | `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md` | Inventory: legacy=0, duplicate=0, unmigrated=0, readiness=1 |
| SR-SCHEMA-012 | Staging database and all long-lived runtime roles admit against Alembic 0045 credential-retirement schema | INTEGRATION_VERIFIED | schema/release admission + role runtimes | clean-room locked build + live Railway admission | `0044_broker_credential_envelope`, `0045_mt5_credential_retirement` | Analytics `4d0bf12c...`; engine `7aac8cf2...`; delivery `2eaf24e7...`; frontdoor `7abdb8e6...` |
| SR-SEC-013 | Counts-only broker credential inventory emits no credential values and confirms staging legacy-secret retirement | INTEGRATION_VERIFIED | `scripts/broker_credential_inventory.py` | `tests/test_broker_credential_inventory.py` | evidence doc above | Deployment `a41c2703-63a8-4d60-9437-f85c349f7823`; envelope_v1 rows=0, legacy rows=0 |
