# SignalRankAI Completion and Verification Report

Date: 2026-07-25
Local branch: `agent/signalrank-core-runtime-hardening`
First isolated hardening commit: `0782d48`

## Executive verdict

The supplied SignalRankAI snapshot has been consolidated into a safe, locally verified Railway-staging candidate. The code compiles, the full available suite passes, environment contracts validate, the schema has one migration head, the Railway entrypoint passes a bounded simulation, and the 100,000-user fanout planner is deterministic and duplicate-free.

The project is **not yet honestly production-ready** because this execution did not have an authenticated Railway connection, real provider credentials/network proof, or a writable GitHub integration. The release guard remains deliberately blocked until a real natural signal completes fresh OHLC, final quote validation, Telegram delivery, delivery proof, active-message persistence, `WATCHING_ENTRY`, entry touch, outcome provenance, and an elapsed soak.

## Core corrections completed

### Market data

- Safe default asset concurrency of two.
- Provider-specific semaphores wrap network calls.
- Maximum two compatible provider attempts per timeframe.
- Real in-flight request coalescing.
- Required timeframes fetched and validated before optional timeframes.
- Child tasks cancelled and awaited after timeout.
- Orphan-task and runtime configuration observability.
- Optional `yfinance` import behaviour corrected.

### Assets and sessions

- Canonical asset registry introduced and propagated.
- Crypto-fiat pairs no longer default to US equity hours.
- Regional index calendars/classification corrected.
- Macro/yield/volatility instruments classified analysis-only by default.
- Unknown symbols fail closed.

### Database and workers

- Canonical DB session priority/label/timeout interface.
- Production legacy call patterns removed.
- Safe pool profile retained for staging.
- Duplicate realtime outcome ownership removed.
- Explicit migration-at-boot failure now stops startup.

### Delivery and lifecycle

- Empty candidate lists return before audience, Redis, DB or background work.
- Delivery/outcome provenance is proof-gated.
- Live outcomes require successful delivery, Telegram metadata, confirmation time and valid state.
- Paper, shadow, backtest, walk-forward and legacy-unverified categories are separate.
- Safe owner test delivery does not create trades or performance records.

### User and owner diagnostics

Implemented and registered:

- `/why_no_signal`
- `/delivery_eligibility`
- `/ohlc_health`
- `/asset_capability`
- `/asset_class_test`
- `/all_asset_test_status`
- `/owner_test_delivery`

### Environment and deployment

- Hermetic local-test profile.
- Railway staging profile.
- Production template.
- Canonical root Railway environment template.
- Environment validation rejects unsafe fail-open or real-money settings.
- Railway entrypoint simulation verifies health and webhook queueing with real integrations disabled.

### Scale foundation

- Deterministic sharded fanout planner.
- 100,000-recipient planning test completed with zero duplicates and zero omissions.
- Capacity model documents staged infrastructure rather than claiming instant Telegram delivery.

## Verification results

- Full tests: 562 passed, 1 skipped, 0 failed.
- Skip reason: local container lacks a compatible `pyarrow` binary; `pyarrow` is declared in `requirements.txt` so Railway/CI must run the Parquet contract.
- Schema audit: pass; 20 revisions; one head `0020_payment_receipts`.
- Architecture smoke: pass.
- Governance validation: pass; 17 documents.
- DB session call audit: pass; no production legacy calls.
- Secret scan: pass; zero findings in deployable source/config.
- Asset registry audit: 40 tested; 36 registry-valid/actionable; 4 analysis-only; 0 failed/unsupported.
- Railway local simulation: health pass; webhook pass; real integrations disabled.
- Fanout planner: 100,000 users; 1,015 batches; 32 shards; 0 duplicates; 0 missing; 9.02 MB peak memory.

## Updated Railway environment

Use `RAILWAY_ENV_UPDATED.env.example` as the import/reference template. Populate secret values only inside Railway. Do not commit actual secrets.

Safety defaults remain:

- auto trading disabled;
- copy trading disabled;
- public payments disabled;
- real payouts disabled;
- final-price timeout/error fail-open disabled;
- websocket ingestion disabled for controlled public testing;
- outcome tracking delivered-only;
- CodexOps read-only;
- Automaton simulation-only.

## Required live staging proof

The next Railway deployment must show:

```text
[db_session_api] legacy_call_sites=0
→ [db_pool_effective_config] safe=true
→ [background_job_ownership] duplicate=false
→ [ohlc_runtime_config] effective_asset_concurrency=2
→ [timeframe_policy]
→ [ohlc_fetch_plan]
→ [ohlc_asset_result] usable=true
→ [ohlc_task_leak_check] orphaned=0
→ market_data_assets > 0
→ strategy_signals > 0
→ [signal_store_timing]
→ [delivery_reserved]
→ [final_quote_validated]
→ [telegram_send_ok]
→ [delivery_proof_write]
→ [active_message_saved]
→ [delivery_completed]
→ WATCHING_ENTRY
```

After a genuine entry touch:

```text
WATCHING_ENTRY → ENTRY_TOUCHED → ACTIVE
→ [outcome_eligibility] category=LIVE_DELIVERED eligible=true
→ valid TP/SL/expiry event
```

## External limitations

- No live Railway deployment was possible because an authenticated Railway tool/CLI was unavailable.
- GitHub repository reads work, but branch creation returned `403 Resource not accessible by integration`; no remote push or PR is claimed.
- Real provider quotas, Telegram rate limits and production database capacity are not proven by local simulation.
- A 24-72 hour soak cannot be fabricated and remains required.

## Release status

- Local code/package: `LOCALLY_VERIFIED`.
- Railway staging candidate: `READY_TO_DEPLOY`.
- Owner internal beta: `BLOCKED_PENDING_LIVE_LIFECYCLE_PROOF`.
- Limited/public/paid release: `BLOCKED_PENDING_STAGING_AND_SOAK`.
- Real auto/copy execution: `DISABLED`.
