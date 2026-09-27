# SignalRank Completion Evidence Ledger

Generated from `docs/architecture/REQUIREMENTS_TRACEABILITY_MATRIX.md` and maintained as the release-facing completion boundary.

## Status vocabulary

Every tracked requirement MUST use exactly one of these statuses:

- `IMPLEMENTED`: code/config exists, but verification evidence is not yet sufficient.
- `VERIFIED`: deterministic repository evidence exists; the `Verification level` column distinguishes unit/contract proof from live staging/integration proof.
- `BLOCKED_EXTERNAL`: SignalRank-side implementation is complete enough to wait safely, but the remaining acceptance proof depends on external credentials, entitlements, legal approval, or representative infrastructure.
- `DEFERRED_WITH_REASON`: intentionally postponed with an explicit technical/product reason.
- `NOT_APPLICABLE`: requirement was evaluated and proven not applicable.

No requirement may be called complete with prose such as “mostly done”, “should work”, or “appears complete”.

## Current release boundary

- Active Alembic head: `0045_mt5_credential_retirement`.
- Blueprint branch: `codex/signalrank-master-blueprint-20260925`.
- Current verified release head: `e7196d4310180b2e901ab020e7041de7c5e18a91`.
- Baseline engine/delivery/analytics runtime head: `93039e2e77800c4aa6b9ba1b1a8ce45797814210`.
- Current component heads: frontdoor `e7196d4310180b2e901ab020e7041de7c5e18a91`; engine/delivery/analytics remain on the certified baseline because subsequent changes are frontdoor/demo-readiness/preparation-only.
- Tracked requirements: **72**.
- `VERIFIED`: **68**.
- `IMPLEMENTED`: **0**.
- `BLOCKED_EXTERNAL`: **4**.
- `DEFERRED_WITH_REASON`: **0**.
- `NOT_APPLICABLE`: **0**.

The four externally blocked items are intentionally fail-closed: optional provider activation, representative 100k/20k scale certification, public copy-marketplace activation, and canonical broker DEMO-account certification. Their blocked status does **not** activate the associated capability.

### Superseding staging evidence — 2026-09-27

The current verified frontdoor release head is
`e7196d4310180b2e901ab020e7041de7c5e18a91`. Frontdoor is deployed at that
exact head; engine, delivery and analytics remain on the compatible certified
baseline `93039e2e77800c4aa6b9ba1b1a8ce45797814210` because the later changes
are frontdoor/demo-readiness/preparation-only.

- clean-room deployment: `22c0e55f-67b5-427f-b34b-aafc2cdc1074`;
- Alembic release-chain: `0045_mt5_credential_retirement` PASS;
- schema audit: PASS, including broker credential-envelope and immutable account-ledger contracts;
- release provenance/SBOM self-check: PASS at `e7196d43...`;
- targeted clean-room suite: **462 passed**;
- staging frontdoor: `713ee164-5002-4499-a7cf-66f67dba0802` at `e7196d43...`;
- staging engine: `ab915899-6177-4608-b8a3-7b539537e25b` at `93039e2e...`;
- staging delivery/outcome: `0683abb8-0128-4266-869c-14f34d821658` at `93039e2e...`;
- staging analytics: `28c378a5-52e8-4f15-a877-e26a82b82ea6` at `93039e2e...`.

All four long-lived roles passed release-source and `0045` schema admission.
The live frontdoor reports `mode=frontdoor`, `http=true`, `telegram=true`,
`engine=false`, `worker=false`, Telegram webhook active, and `/healthz=200`.
The other roles boot only their declared dedicated runtime modes.

### Safe DEMO certification preparation — 2026-09-27

SignalRank-side DEMO onboarding/preparation is now complete up to the external
broker-account boundary. An owned provider-proven DEMO connection gets an
explicit **Prepare DEMO certification** action that performs canonical read-only
provider verification and reconciliation, refuses live/ambiguous accounts,
requires canonical credential readiness + HEALTHY reconciliation, applies a
bounded `DEMO/MANUAL` policy, and leaves execution disabled. A separate terms
acceptance + explicit per-account execution-enable action is still required
before the bounded DEMO execution lifecycle.

- canonical service: `services/demo_certification.py`;
- API: `POST /broker/connections/{connection_id}/demo-certification/prepare`;
- web broker-card action: `Prepare DEMO certification`;
- implementation commits: `daa835c5...`, `17cb26e1...`, `af0f39a2...`;
- focused behavior coverage: `tests/test_demo_account_preflight.py`;
- PWA shell: v24;
- clean-room rollout marker `e7196d43...`: Alembic 0045/schema/provenance PASS,
  **462 targeted tests passed**;
- staging frontdoor `713ee164-5002-4499-a7cf-66f67dba0802`: **356 image-gate tests**
  + readiness PASS, release-source/schema PASS, `mode=frontdoor`,
  `engine=false`, `worker=false`, MetaApi startup probe PASS and
  `/healthz=200`;
- refreshed read-only preflight `e80fa087-d487-40fc-859e-76df71a3b7b7`
  on marker `a77694b5...`: **BLOCKED_EXTERNAL**, broker connections=0,
  activation=false, orders=0, secrets_returned=false.

The remaining DEMO blocker is therefore not hidden application work: an
explicitly owned external DEMO broker account must be linked and its bounded
provider order/modify/close/restart/reconciliation evidence must be captured.
Environment-level broker secrets are never converted into user ownership.

### Frontdoor delivery-terminal maintenance — 2026-09-27

A live staging sweep found the resend scheduler reconsidering one
`EXPIRED_IN_QUEUE` signal every 30 seconds. The repair keeps analytical
signal/outcome lifecycle untouched and persists a bounded
`runtime_state` delivery-terminal marker named
`resend_terminal:<signal_id>` so the same immutable signal version does not
re-enter resend recovery after queue expiry.

- implementation commit: `35ca0ca088d74d5d487b14cc012c0388cf1aae7e`;
- focused regression: `tests/test_resend_terminal_queue_expiry.py`;
- certified rollout commit: `3379cae487d59f1f28edcedb1a1b362a33cef419`;
- clean-room deployment: `5c3a09c9-df98-41b0-b89c-b4b6307fe9c4`;
- clean-room result: Alembic 0045/schema/provenance PASS and **414 targeted tests passed**;
- staging frontdoor deployment: `f3693c26-3d84-44c0-bd1e-090ca203d13f`;
- frontdoor locked-image build: **356 tests passed** plus production-readiness PASS;
- live admission: release-source PASS, Alembic 0045/schema PASS,
  `mode=frontdoor`, `engine=false`, `worker=false`, `/healthz=200`,
  Telegram webhook pending=0;
- post-cutover resend cycles completed without another reference to the prior
  repeatedly-stale signal and without a delivery-terminal marker persistence
  error. That historical signal had already left the active candidate set
  during cutover, so the live run is not represented as a fresh marker-write
  proof; the marker path is covered by the clean-room regression.

## Ledger

| ID | Ledger status | Verification level | Requirement | Implementation / evidence |
|---|---|---|---|---|
| SR-BASE-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Outcome persistence independent of notification fan-out | `services/outcome_reconciliation.py`, outbox repair · `test_v1369_outcome_delivery_recovery.py` · — |
| SR-BASE-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Central `_env_bool` helpers | `core/env.py` · suite-wide · — |
| SR-BASE-003 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Performance reconciliation per-user failure isolation | `services/performance_ledger.py` · `test_v1368_performance_scale_hotfix.py` · — |
| SR-BASE-004 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Terminal outcome ordering (tp1→tp2/tp3 progression) | `core/outcome_ordering.py` · outcome tests · — |
| SR-EVENT-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Full envelope identity (aggregate/trace/deployment/payload hash) | `core/durable_event_stream.py` · `test_v20_event_platform.py` · `DURABLE_EVENT_STREAM_ENABLED` |
| SR-EVENT-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Canonical event catalogue + validation | `core/event_catalogue.py` · `test_v20_event_platform.py` · — |
| SR-EVENT-003 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Transactional outbox contract | `core/transactional_outbox.py` · `test_v20_event_platform.py` · — |
| SR-EVENT-004 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Idempotent consumer inbox (exactly-once logical) | `core/transactional_outbox.py` · `test_v20_event_platform.py` · — |
| SR-EVENT-005 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Bounded relay, backoff, dead-letter | `core/transactional_outbox.py` · `test_v20_event_platform.py` · — |
| SR-EVENT-006 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Partitioned transport + consumer groups + reclaim | `core/durable_event_stream.py`, `core/redis_streams.py` · connector-level event/stream tests · `DURABLE_EVENT_STREAM_ENABLED` |
| SR-PROVIDER-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Typed failure taxonomy (§8 list) | `data/provider_failures.py` · `test_v20_provider_layer.py` · — |
| SR-PROVIDER-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | HTTP status classification + retry policy | `data/provider_failures.py` · `test_v20_provider_layer.py` · — |
| SR-PROVIDER-003 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Capability manifest + certification states | `data/provider_contracts.py` · `test_provider_catalog_and_certification.py` · — |
| SR-PROVIDER-004 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Canonical instrument model (tick/minimums/aliases/status) | `data/canonical_instruments.py` · `test_v20_provider_layer.py` · — |
| SR-PROVIDER-005 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Quote trust policy (freshness, provenance, no candle-as-quote) | `data/provider_types.py` · provider tests · — |
| SR-PROVIDER-006 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Circuit breakers + quarantine | `core/circuit_breaker.py` · `test_provider_registry_fail_closed.py` · — |
| SR-PROVIDER-007 | VERIFIED | STAGING / INTEGRATION | Every enabled/claimed market-data provider is independently live/public/sandbox certified before being treated as production-ready | provider catalogue/adapters, `scripts/certify_providers.py`, explicit provider enable gates · `tests/test_provider_catalog_and_certification.py`, `tests/test_provider_registry_fail_closed.py`, `tests/test_provider_live_contract_repairs.py` · Staging certification `65c8d1a6-0358-49ee-91b2-aa8b60718fda` on commit `12e2427e...`: all enabled providers live/public verified; exit=0; see `docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md` |
| SR-PROVIDER-008 | BLOCKED_EXTERNAL | EXTERNAL PREREQUISITE | Optional providers/venues that are disabled by policy are activated only after their exact credential, plan, licence, regional and execution/reconciliation requirements are externally certified | Explicit opt-in gates remain off; `requirements/external_activation_requirements.yaml` + `scripts/external_blocker_preflight.py provider` validate credential presence and external entitlement/licensing/certification evidence without returning secret values or activating a gate · `tests/test_external_blocker_preflight.py` · Staging deployment `3a95addd-510d-47d2-acd8-f2257f529ea4`: FMP/Alpha blocked on missing external approval/certification evidence; OANDA/FRED additionally missing required credential/config prerequisites; every result `activation_performed=false`; see `docs/evidence/EXTERNAL_BLOCKER_PREFLIGHT_20260927.md` |
| SR-RISK-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Portfolio risk authority (exposure + breakers) | `core/risk_authority.py` · `test_v20_risk_authority.py` · — |
| SR-RISK-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Kill-switch gate on every admission | `core/risk_authority.py`, `core/financial_activation.py` · risk + activation tests · `GLOBAL_EXECUTION_KILL_SWITCH` |
| SR-RISK-003 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Append-only financial ledger | `core/financial_ledger.py` · `test_v20_financial_ledger.py` · — |
| SR-RISK-004 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Compensating corrections + double entry + imbalance detection | `core/financial_ledger.py` · `test_v20_financial_ledger.py` · — |
| SR-ML-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Calibration rules (no uncalibrated score as probability) | `engine/ml_weighting.py` + telemetry · ML tests · — |
| SR-ML-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Champion/challenger + shadow promotion + rollback | `ml/train_model.py`, `engine/ml.py`, durable model artifact store · `tests/test_ml_champion_challenger_governance.py`, `tests/test_ml_registry.py`, `tests/test_ml_durable_artifact_sync.py` · `ADAPTIVE_LEARNING_ENABLED` |
| SR-ML-003 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Full model registry / dataset-run-parent lineage / leakage gates | `ml/model_registry.py`, `ml/train_model.py`, adaptive dataset/WFO contracts · `tests/test_ml_registry.py`, `tests/test_adaptive_dataset_and_wfo.py`, ML schema/leakage tests · — |
| SR-SEC-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Secret redaction in logs | prior repair pass; `core/security.py` · secret-leak tests · — |
| SR-SEC-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Signed webhook verification from raw body | `payments/paystack_events.py` · webhook tests · — |
| SR-SEC-003 | VERIFIED | STAGING / INTEGRATION | Threat model documented against the deployed 0045 architecture and residual-risk boundary | `docs/security/THREAT_MODEL.md` · release/security contract review + staging 0045 evidence · — |
| SR-SEC-004 | VERIFIED | STAGING / INTEGRATION | Versioned, account-bound envelope encryption and key rotation for broker credentials | `services/broker_credentials.py`, canonical broker connection writer, `0044_broker_credential_envelope` · `test_broker_credential_envelope.py` · `BROKER_CREDENTIAL_KEYRING_JSON`, `BROKER_CREDENTIAL_ACTIVE_KEY_ID` |
| SR-SEC-005 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Deterministic CycloneDX 1.5 dependency SBOM and release provenance bind the locked graph, Dockerfile, current release contract, exact commit/branch and Alembic head | `scripts/generate_release_provenance.py`, `requirements.lock` · `tests/test_release_provenance.py`; clean-room provenance self-check · external signing key remains separate |
| SR-SCALE-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | SLO registry + error budgets + degradation | `core/slo_registry.py` · `test_v20_slo_registry.py` · — |
| SR-SCALE-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Bounded queues / backpressure / DLQ | `core/redis_streams.py`, `core/transactional_outbox.py` · queue tests · — |
| SR-SCALE-003 | BLOCKED_EXTERNAL | EXTERNAL PREREQUISITE | 100k-user / 20k-concurrent representative infrastructure certification | `scripts/load_certification.py`, `requirements/scale_profiles.yaml`, SLO/queue/role architecture, and `scripts/external_blocker_preflight.py scale` · `tests/test_load_certification.py`, `tests/test_external_blocker_preflight.py` · Staging deployment `3a95addd-510d-47d2-acd8-f2257f529ea4` correctly rejected non-certification input for kind/profile/PASS/claim/concurrency/load-summary requirements and returned `capacity_claim_allowed=false`; see `docs/evidence/EXTERNAL_BLOCKER_PREFLIGHT_20260927.md` |
| SR-OBS-010 | VERIFIED | STAGING / INTEGRATION | Canonical SLO metrics have operational dashboards, alert thresholds, explicit owners, automatic degradation actions and incident runbook coverage | `core/slo_registry.py`, `core/telemetry.py`, `observability/slo_operations.py`, Prometheus/Grafana artifacts · `tests/test_observability_operations_contract.py` + clean-room gate · Clean-room `e2ef6763-34a8-4f2c-9e85-00e978e82256`: 0045/schema/provenance PASS; 411 targeted tests PASS on runtime commit `93039e2e...` |
| SR-NOTIF-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Notification outbox repair bounded | outcome reconciliation · v1.3.6.9 tests · — |
| SR-NOTIF-002 | VERIFIED | STAGING / INTEGRATION | Dedicated fan-out reservation/idempotency boundary plus durable terminal suppression of queue-expired resend candidates | `db/pg_features.py`, `delivery/service.py`, outbox/receipt layers, `signalrank_telegram/bot.py` · `tests/test_phase4_pass3_delivery_reliability.py`, `tests/test_delivery_fanout_planner.py`, `tests/test_resend_terminal_queue_expiry.py` · clean-room `5c3a09c9...` 414 PASS; frontdoor `f3693c26...` healthy on 0045 |
| SR-ORDER-001 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Canonical monotonic order/execution state machine with one position-state projection | `core/execution_state_machine.py`, MT5/Bybit routers and reconcilers · `tests/test_execution_state_machine.py`, `tests/test_canonical_broker_entrypoints.py` · `REAL_EXECUTION_ENABLED=0` |
| SR-ORDER-002 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Copy-trade execution safety foundation requires explicit copy consent, leader provenance, follower/account risk, account policy, kill switch and duplicate protection before canonical broker routing | `services/ecosystem_policy.py`, `execution/service.py`, MT5/Bybit routers, release/financial guards · `tests/test_copy_trade_safety_foundation.py`, broker execution tests · `COPY_TRADE_ENABLED=0` by default |
| SR-MARKETPLACE-001 | BLOCKED_EXTERNAL | EXTERNAL PREREQUISITE | Public copy marketplace / publisher trust / suitability / commercial strategy-bot activation | Copy-execution safety primitives and canonical broker/risk layers are present; `requirements/external_activation_requirements.yaml` + `scripts/external_blocker_preflight.py marketplace` require publisher identity, follower consent/revocation, suitability, performance disclosure, abuse controls, jurisdiction/commercial approval and runtime copy-safety evidence · staging deployment `3a95addd-510d-47d2-acd8-f2257f529ea4` returned `public_marketplace_claim_allowed=false` with all required external/runtime evidence still missing and `activation_performed=false`; see `docs/evidence/EXTERNAL_BLOCKER_PREFLIGHT_20260927.md` |
| SR-ID-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | All broker-account object access is scoped by canonical `users.id + connection_id`; no BOLA/IDOR through normal policy, ledger, execution or evidence routes | `services/account_policies.py`, `services/broker_connections.py`, `services/trading_account_ledger.py`, `services/execution_evidence.py`, `web/platform_api.py` · `tests/test_broker_account_bola_idor.py` · addendum § identity/isolation \| Clean-room targeted suite; commits `b3ce41e`, `ffb6460` |
| SR-ACCOUNT-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | One canonical user may own multiple immutable broker connections with explicit PAPER/DEMO/LIVE_PERSONAL/PROP classification | `services/broker_connections.py`, `db/models.py` · `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` · `0041_broker_connection_registry`, `0043_account_execution_policy` \| Conservative policy creation on every new connection; PR #71 |
| SR-ACCOUNT-011 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Every connected account owns a separately versioned execution/risk policy; material edits clear certification and disable execution | `core/account_policy.py`, `services/account_policies.py`, `web/platform_api.py` · `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` · `0043_account_execution_policy` \| Commits `cfd4b30`, `3e53004`, `289bb96` |
| SR-EXEC-020 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Execution destination claims and prior-execution evidence are scoped to trading account, not only user+signal | `core/execution_claims.py`, `services/execution_evidence.py`, `services/broker_signal_router.py` · `tests/test_multi_account_prop_policy.py`, `tests/test_broker_account_bola_idor.py` · addendum § account selection \| Account collisions removed; explicit account required when ambiguous |
| SR-EXEC-021 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Telegram manual execution uses short-lived opaque server-bound account-selection tokens; raw connection IDs are not trusted from callback payloads | `services/broker_account_selection.py`, `signalrank_telegram/bot.py`, callback registry · `tests/test_canonical_broker_entrypoints.py`, `tests/test_broker_account_bola_idor.py` · `requirements/callback_registry.yaml` \| Policy-version/owner/signal binding verified in targeted suite |
| SR-EXEC-022 | VERIFIED | REPOSITORY / UNIT-CONTRACT | MT5 and provider-neutral execution ledgers persist the canonical `connection_id` for new orders; ambiguous historical rows are never guessed | `services/mt5_signal_router.py`, `services/bybit_signal_router.py`, `db/models.py` · `tests/test_final_cross_channel_parity_20260925.py` · `0043_account_execution_policy` \| 0043 backfills MT5 only where user+provider account maps uniquely |
| SR-PROP-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | PROP rules are deterministic, versioned and configuration-driven rather than hard-coded to a named firm | `core/account_policy.py`, `services/account_policies.py` · `tests/test_multi_account_prop_policy.py` · architecture companion \| Generic hard-rule engine commit `9f75536`; tests `b1e2e42` |
| SR-PROP-011 | VERIFIED | REPOSITORY / UNIT-CONTRACT | PROP certification is an owner/admin-only operation bound to an exact policy version with certifier provenance | `services/account_policies.py`, `web/platform_api.py`, `db/models.py` · `tests/test_multi_account_prop_policy.py`, `tests/test_final_cross_channel_parity_20260925.py` · `0043_account_execution_policy` \| Server-side authority + `admin_events`; commits `5ac80b...`/PR #71 |
| SR-RISK-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Per-account hard limits cover trade risk, daily/weekly/total loss, leverage, positions, spread/slippage, confidence/R:R, strategy/instrument and trading windows | `core/account_policy.py`, MT5/Bybit routers · `tests/test_multi_account_prop_policy.py` · `0043_account_execution_policy` \| Deterministic reason codes; real accounts fail closed without verified loss baselines |
| SR-RECON-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Reconciliation is per account and material discrepancy/auth/disconnect states disable execution and freeze the affected policy | `services/account_policies.py`, `broker_reconciliation_state` · `tests/test_final_cross_channel_parity_20260925.py` · `0043_account_execution_policy` \| Durable safety audit event; commit `f4d0eec` |
| SR-LEDGER-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Broker account financial/trade evidence is persisted in an append-only, account-owned, provider-idempotent canonical ledger | `services/trading_account_ledger.py`, `db/models.py` · `tests/test_trading_account_ledger.py`, `tests/test_broker_account_bola_idor.py`, parity tests · `0043_account_execution_policy`; immutable DB trigger \| Commits `b486ddc`, `0585e11`; schema gate requires table |
| SR-LEDGER-011 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Bybit snapshots, orders, positions, realized P/L and provider-reported fees feed the canonical account ledger without inferred values | `services/bybit_signal_router.py`, `services/bybit_reconciler.py` · source/parity + ledger tests · architecture companion \| Commits `11c105d`, `b5c7980`; live-provider certification remains a separate gate |
| SR-LEDGER-012 | VERIFIED | REPOSITORY / UNIT-CONTRACT | MT4/MT5 account snapshots/orders plus exact MetaApi deal history feed canonical ledger; authoritative realized P/L, commission, swap and provider fees are ingested without symbol-only attribution | `services/mt5_signal_router.py`, `services/mt5_client.py`, `services/mt5_reconciler.py`, `worker/worker.py` · `tests/test_mt5_reconciliation_ledger.py`, `tests/test_v131_live_financial_activation.py`, parity tests · architecture companion \| Commits `d9a2fdb`, `b80a846`, `b9d39ff`, `c400e4a`; live MetaApi provider certification remains a separate runtime gate |
| SR-AUDIT-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Policy edits, user safety freezes/unfreezes, operator PROP certification and reconciliation safety blocks are durably audited | `services/account_policies.py`, `AdminEvent` · `tests/test_final_cross_channel_parity_20260925.py` · architecture companion \| Commit `f4d0eec`; no credentials stored in audit details |
| SR-PERF-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | DEMO, LIVE_PERSONAL and PROP broker performance is composed per connection and not shown as a mixed user headline | `web/platform_api.py`, `web/platform_app/app.js` · `tests/test_final_cross_channel_parity_20260925.py` · architecture companion \| Commits `56ab2cc`, `5a0ad98`; mixed aggregates retained only as labelled diagnostics |
| SR-WEB-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Web account UI exposes account policy, PROP rules, safety freeze, reconciliation and selected-account ledger evidence | `web/platform_app/index.html`, `app.js`, `platform_api.py` · parity tests · PWA cache rotated with each contract change \| Policy/ledger UI commits `ff093aa`, `266a077` and later |
| SR-BROKER-VERIFY-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Owned MT4/MT5/Bybit accounts have one canonical read-only verification path shared by web and Telegram; verification cannot place orders, expose credentials, or bypass canonical user+connection ownership | `services/broker_verification.py`, `web/platform_api.py`, `web/platform_app/app.js`, `signalrank_telegram/commands.py` · `tests/test_canonical_broker_entrypoints.py`, `tests/test_broker_account_bola_idor.py` · Alembic 0045 unchanged; PWA shell v17 \| Clean-room `e966d441...`: release/schema/provenance PASS, 399 targeted tests PASS |
| SR-SCHEMA-010 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Runtime admission requires policy, reconciliation, canonical account ledger, decision provenance, and account-scoped execution columns at Alembic head 0043 | `scripts/assert_database_schema.py`, `scripts/staging_runtime_proof.py` · `tests/test_blueprint_certification_safety.py` · `0043_account_execution_policy` \| Commits `32154e3`, `f4645f5` |
| SR-SCHEMA-011 | VERIFIED | STAGING / INTEGRATION | Shared staging DB is migrated to 0043 and passes post-migration runtime proof with live financial flags off | controlled migration/certification tooling · runtime certification suite · staging only; production untouched \| Migration deployment `ec5be43c-0658-4398-93fc-50917b387158`: 0042→0043, schema gate PASS, runtime proof PASS, zero blockers, kill switch on and live-financial flags off |
| SR-RUNTIME-010 | VERIFIED | STAGING / INTEGRATION | Frontdoor, engine, delivery/worker and analytics roles can prove exact release identity and 0043 schema compatibility without starting business loops | `start.sh`, `scripts/quiescent_role.py`, `runtime/roles.py` · `tests/test_quiescent_role_certification.py`; clean-room targeted suite · staging-only quiescent certification \| Analytics `284ed63b-0716-48e4-9498-41dc270c0e6f`, engine `a67a3f14-5944-4e27-b8c3-245c1a3bd96b`, worker `d4a490dc-ce9f-4e30-9fae-172ac94cbe3f`, frontdoor `a562a609-b533-46e9-aa2b-bbffcc5bbdc4`; all release/schema gates PASS, business loops disabled, production untouched |
| SR-RUNTIME-011 | VERIFIED | STAGING / INTEGRATION | Long-lived staging analytics, delivery, engine and frontdoor roles run against the certified 0043 schema with explicit non-overlapping ownership | `runtime/roles.py`, `runtime/analytics.py`, `runtime/delivery.py`, `runtime/engine.py`, `runtime/frontdoor.py`, `start.sh` · clean-room + locked Docker build gate + live Railway admission · `docs/evidence/STAGING_0043_ROLE_CERTIFICATION_20260925.md` \| Analytics `af352868-be5d-4012-90fc-ca56dc06252f`; delivery `0e82f4b8-d4d9-4bf7-bcfe-a87e3a8be044`; engine `de79e783-f33a-4cc2-8871-b6f3bc60c470`; frontdoor `a3d77cb6-5933-4634-83be-56b6b6426702`; all on 0043 + certified dependency lock, release/schema gates PASS |
| SR-MARKET-010 | VERIFIED | STAGING / INTEGRATION | Engine supports crypto, FX, equities, indices and commodities and applies market-session calendars before cycle admission | `engine/core.py`, `data/class_universe.py`, `data/database_universe.py`, market/session classifiers · provider-discovery/build tests + live staging engine evidence · staging engine deployment \| Active engine: crypto usable=250, FX=16, equities=23, indices=5, commodities=4; non-crypto zero-open counts during first post-cutover cycle were explicitly caused by Friday/session closures, not crypto-only filtering |
| SR-WEB-011 | VERIFIED | STAGING / INTEGRATION | Public staging frontdoor serves HTTP + Telegram without owning engine/worker loops and exposes a healthy external dashboard | `runtime/frontdoor.py`, `railway_main.py`, `start.sh` · locked build gate + live /healthz + external browser check · staging frontdoor deployment \| Deployment `a3d77cb6-5933-4634-83be-56b6b6426702`: Alembic 0043/schema PASS, frontdoor DB admission active, Uvicorn 8080, /healthz=200, Telegram webhook pending=0 |
| SR-RELEASE-010 | VERIFIED | STAGING / INTEGRATION | Staging rollout markers cannot automatically deploy production and role-specific watch paths prevent cross-role restart fan-out | Railway watch-pattern rollout contract + release-source gate · live deployment history · staging rollout evidence \| Frontdoor/engine/delivery/analytics production marker deployments were SKIPPED; staging frontdoor marker rebuilt only frontdoor while other staging roles skipped; production database untouched |
| SR-RELEASE-011 | VERIFIED | STAGING / INTEGRATION | Runtime dependency graph is reproducible and staging roles use the certified lock rather than floating direct dependency ranges | `requirements.lock`, Dockerfile `pip install --no-deps` + `pip check` · locked build gate; dependency lock tests · staging role deployments \| Analytics `3a1e072`, delivery `3b5ff87`, engine `b6bfdec`, frontdoor `4e6575d`; locked images passed repository build/readiness gates |
| SR-SCALE-010 | VERIFIED | STAGING / INTEGRATION | Adaptive candle persistence cannot monopolize the tiny engine DB pool under foreground pressure | `engine/adaptive/candle_store.py` · `test_adaptive_and_shadow_writes_are_durable_background_work`, `test_adaptive_candle_pressure_requeues_full_batch` · engine runtime evidence \| Engine `de79e783-f33a-4cc2-8871-b6f3bc60c470`: foreground-reserve deferrals were immediate, full batches requeued, bounded 2-snapshot/400-candle write succeeded, 5/5 candle fetch remained responsive, no warning/error severity |
| SR-SEC-010 | VERIFIED | STAGING / INTEGRATION | Broker credential ciphertext is bound to canonical user + connection + provider + connector + revision and rejects context replay | `services/broker_credentials.py` · `tests/test_broker_credential_envelope.py` · `0044_broker_credential_envelope` \| Clean-room + long-lived staging 0045 role admission |
| SR-SEC-011 | VERIFIED | REPOSITORY / UNIT-CONTRACT | Broker key rotation supports previous-key reads/current-key writes, disables execution on rotation and records non-secret audit provenance | `services/broker_credentials.py`, `AdminEvent` · `tests/test_broker_credential_envelope.py` · credential keyring contract \| Missing/unknown keys fail closed |
| SR-SEC-012 | VERIFIED | STAGING / INTEGRATION | Duplicate MT5 password persistence is retired after canonical credential-envelope migration | `0045_mt5_credential_retirement`, `services/mt5_client.py` · `tests/test_broker_credential_envelope.py`, inventory tests · `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md` \| Inventory: legacy=0, duplicate=0, unmigrated=0, readiness=1 |
| SR-SCHEMA-012 | VERIFIED | STAGING / INTEGRATION | Staging database and all long-lived runtime roles admit against Alembic 0045 credential-retirement schema | schema/release admission + role runtimes · clean-room locked build + live Railway admission · `0044_broker_credential_envelope`, `0045_mt5_credential_retirement` \| Analytics `4d0bf12c...`; engine `7aac8cf2...`; delivery `2eaf24e7...`; frontdoor `7abdb8e6...` |
| SR-SEC-013 | VERIFIED | STAGING / INTEGRATION | Counts-only broker credential inventory emits no credential values and confirms staging legacy-secret retirement | `scripts/broker_credential_inventory.py` · `tests/test_broker_credential_inventory.py` · evidence doc above \| Deployment `a41c2703-63a8-4d60-9437-f85c349f7823`; envelope_v1 rows=0, legacy rows=0 |

| SR-DR-010 | VERIFIED | STAGING / INTEGRATION | Full staging PostgreSQL backup/restore drill proves bounded dump, isolated restore, 0045 schema/data recovery, immutable-ledger trigger recovery and cleanup without source/production mutation | `scripts/staging_backup_restore_drill.py`, `Dockerfile.restore-drill` · `tests/test_staging_backup_restore_drill.py` · deployment `59a52067-b83f-46bb-83f6-67080b818c7d`: dump 199,493,675 bytes, restore 297.755s, restored head 0045, 48,132 signals + 6 users, cleanup PASS, source/production mutation false |
| SR-DEMO-010 | BLOCKED_EXTERNAL | EXTERNAL PREREQUISITE | SignalRank-side DEMO onboarding/preparation is complete and fail-closed; the remaining acceptance proof requires an explicitly owned external DEMO account plus bounded provider order/modify/close/restart/reconciliation evidence before any demo/live promotion claim | `services/demo_certification.py`, `scripts/demo_account_preflight.py`, canonical broker onboarding/verification/policy/reconciliation/execution layers · `tests/test_demo_account_preflight.py` · safe-prepare frontdoor `713ee164-5002-4499-a7cf-66f67dba0802` at `e7196d43...`; refreshed preflight `e80fa087-d487-40fc-859e-76df71a3b7b7` on marker `a77694b5...`: broker connections=0, activation=false, orders=0, secrets returned=false; exact blockers recorded in `docs/evidence/STAGING_DEMO_ACCOUNT_PREFLIGHT_20260927.md` |


## Release rule

A production/live promotion report may only state “complete” when:

1. every in-scope requirement is `VERIFIED` or `NOT_APPLICABLE`;
2. any `BLOCKED_EXTERNAL` requirement remains disabled/fail-closed and is explicitly excluded from the promoted scope;
3. there are no unexplained `IMPLEMENTED` or `DEFERRED_WITH_REASON` requirements;
4. the release provenance, schema head, dependency lock, source SHA, staging certification and runtime-role evidence all refer to the same release candidate.

This ledger is evidence bookkeeping, not a substitute for the underlying tests, staging proofs, provider certifications, or financial safety gates.
