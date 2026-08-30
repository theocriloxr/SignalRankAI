# Phase 4 Pass 4 — Outcome Tracker Redesign

Date: 2026-07-18  
Branch: `fix-2`  
Canonical implementation checkpoint observed during the pass: `a4a3729`  
Status: complete for Pass 4; Pass 5 has not started

## Outcome

The live outcome path now uses one canonical uppercase lifecycle graph, one typed and trusted quote per unique asset per scan cycle, database-locked monotonic transitions, sequential TP ledger progression, versioned outcome snapshots, snapshot-first `Check Outcome` callbacks, and notification delivery outside the critical transition transaction.

Post-commit projection repair is also covered: if lifecycle CAS commits but the downstream `Outcome` upsert fails, a later scan repairs the missing or lagging outcome row from durable lifecycle truth without replaying or downgrading the transition.

The Pass 4 acceptance criterion is met by focused tests for TP1 → TP2 → TP3 progression, forbidden downgrades, replay, stale/provider-outage behavior, same-asset quote batching, lifecycle/outcome projection recovery, snapshot version/TTL/next-target data, and snapshot-first callback handling.

## Canonical lifecycle contract

The required states are:

```text
WATCHING_FOR_ENTRY
ACTIVE_TRADE
TP1_HIT
TP2_HIT
TP3_HIT
SL_HIT
BREAKEVEN_STOP
MISSED_ENTRY
EXPIRED
```

Terminal states cannot be reopened or overwritten. TP state can only remain equal or progress forward. `SL_HIT` is valid before any TP; after TP progress, a stop is represented by `BREAKEVEN_STOP`. Legacy values such as `new`, `entry_hit`, `tp1`, `tp`, `sl`, `partial_win_be`, and `time_stop` normalize through the same pure graph.

`SignalLifecycle` is authoritative. `Outcome` and Redis are read projections. Redis TP progress can no longer advance transition decisions beyond durable database state.

## Implementation

### Asset-batched trusted quotes

- Active and backfill signals are combined before quote acquisition.
- The tracker canonicalizes and deduplicates assets, then performs exactly one logical quote request per unique asset per cycle.
- Every signal for that asset receives the same typed observation.
- The existing final-quote trust policy rejects missing source time, previous-close values, stale observations, unhealthy providers, open breakers, low-confidence quotes, and other untrusted provider results.
- Provider failure updates only snapshot trust/freshness information. It cannot mutate lifecycle or outcome truth.
- An unavailable refresh preserves the prior snapshot's last known price and quote time while marking the new provider observation untrusted.

### Monotonic transition CAS and ledger

- `core/signal_lifecycle.py` owns the only canonical graph and legacy mapper.
- Lifecycle observation and event writes use critical DB priority.
- Transition writes lock the `signal_lifecycles` row with `SELECT ... FOR UPDATE` before checking the graph and committing an event.
- Forbidden, late, duplicate, or reordered events cannot downgrade state.
- A price crossing multiple targets emits and commits TP1, TP2, and TP3 in ledger order rather than recording only the highest target.
- Entry gating, missed-entry expiry, normal SL, protected stop after TP, and time-stop behavior remain supported.
- When lifecycle truth is ahead of the `Outcome` projection, the tracker repairs the projection monotonically using the last durable lifecycle price.
- The existing `OUTCOME_LIFECYCLE_ENABLED=0` compatibility path still persists outcomes without requiring lifecycle CAS.

### Outcome snapshots and callbacks

`engine/outcome_snapshots.py` defines snapshot version `phase4-pass4-v1` with:

- signal ID, asset, and direction;
- canonical lifecycle state and highest TP;
- last trusted price and provider quote time;
- next target and signal expiry;
- provider identity, trust decision, and reason;
- projection source, update time, and schema version.

Snapshots use a bounded Redis TTL and reject unsupported versions. A database fallback can rebuild the projection on cache miss. Both the concrete bot callback and the global fallback callback check Redis before opening a database session; snapshot failures safely fall back to the existing DB response path.

### Notification separation and compatibility

- `record_lifecycle_event` commits lifecycle state, ledger event, and confirmed-recipient notification rows without Telegram network I/O.
- The separate pending-notification dispatcher runs after transition scanning, outside row locks and critical transactions.
- Only confirmed/reconciled successful signal deliveries are eligible lifecycle recipients.
- The existing idempotent, tier-aware `OutcomeNotification` outbox remains as a compatibility fallback.
- `upsert_outcome(queue_notifications=False)` prevents double-enqueue; the tracker queues the fallback exactly once, and successful lifecycle delivery cross-marks the corresponding fallback row delivered.

### Migration boundary

No migration was introduced. The existing lifecycle, tracking-event, lifecycle-notification, outcome, and outcome-notification tables support this compatibility pass. Schema-chain reconciliation remains in its ordered later pass.

## Files

- `core/signal_lifecycle.py` — canonical state enum, graph, legacy normalization, outcome/lifecycle projection maps, monotonic guards.
- `engine/signal_lifecycle.py` — locked lifecycle observation/transition service and network-separated notification dispatcher.
- `engine/realtime_outcome_tracker.py` — typed quote batching, DB-authoritative TP progress, ordered transition requests, projection repair, snapshot publication, and outbox compatibility.
- `engine/outcome_snapshots.py` — versioned Redis snapshot, DB fallback, staleness handling, and callback formatter.
- `db/pg_features.py` — explicit outcome-upsert notification control.
- `signalrank_telegram/bot.py` — snapshot-first concrete `Check Outcome` callback.
- `signalrank_telegram/callback_handlers.py` — snapshot-first global fallback callback.
- `tests/test_phase4_pass4_outcome_tracker_redesign.py` — twelve Pass 4 contract and failure-path tests.

## Verification

### Static verification

```powershell
python -m compileall -q core/signal_lifecycle.py db/pg_features.py engine/signal_lifecycle.py engine/outcome_snapshots.py engine/realtime_outcome_tracker.py signalrank_telegram/bot.py signalrank_telegram/callback_handlers.py
git diff --check
```

Result: passed. The only output was Git's existing LF-to-CRLF working-tree notice.

### Focused Pass 4 and compatibility suite

```powershell
python -m pytest tests/test_phase4_pass4_outcome_tracker_redesign.py tests/test_outcome_delivery_contract.py tests/test_time_stop_outcome_persistence.py tests/test_realtime_outcome_tracker_user_perf_ids.py tests/test_runtime_log_regressions.py -q
```

Result: **31 passed**, 1 inherited Eventlet deprecation warning, in 10.42 seconds.

### Adjacent outcome/lifecycle/callback regression suite

```powershell
python -m pytest tests/test_phase4_pass4_outcome_tracker_redesign.py tests/test_time_stop_outcome_persistence.py tests/test_realtime_outcome_tracker_user_perf_ids.py tests/test_realtime_outcome_tp_tiers.py tests/test_realtime_outcome_delivery_tier_gates.py tests/test_outcome_integration_multi_tp.py tests/test_outcome_delivery_contract.py tests/test_delivery_outcome_news_hardening.py tests/test_callback_handler.py tests/test_runtime_log_regressions.py -q
```

Result: **47 passed**, 1 inherited Eventlet deprecation warning, in 10.41 seconds.

### Canonical deterministic repository suite

```powershell
$testFiles = @(rg --files tests -g 'test_*.py' | Where-Object { $_ -notlike '*test_broker_permission_validation.py' } | Sort-Object)
python -m pytest @testFiles -q
```

Final result: **470 passed, 28 failed, 2 errors**, 34 warnings, in 60.12 seconds.

The final Pass 3 baseline was **455 passed, 31 failed, 2 errors**. Pass 4 adds exactly twelve passing contract tests and repairs the three inherited outcome/session-shim failures. No new failure or error category was introduced.

The 28 remaining inherited failures are the previously documented admin-pulse source contract, missing Paystack/web compatibility exports, Flask/ASGI mismatch, Railway pool expectation, readiness/scheduler imports, free-signal visibility source contract, Windows default-encoding source read, telemetry ASGI mismatch, and engine dispatch source contract. The two inherited errors remain Windows ACL failures creating `tmp_path` under `C:\Users\sammm\AppData\Local\Temp\pytest-of-Theophilus`.

The deterministic command excludes the same inherited collection blocker as Passes 2 and 3: `tests/test_broker_permission_validation.py` imports the missing `verify_api_key` symbol from `web.app`.

## Pass boundary

Pass 4 is complete. Tier-policy unification, entitlement matrices, and tier-specific product/notification behavior belong to Phase 4 Pass 5 and were not implemented here.

Live staged PostgreSQL concurrency, Redis outage/reconnect, provider-load, and Telegram callback-latency canaries remain operational verification requirements before production readiness. This pass does not claim public launch readiness.
