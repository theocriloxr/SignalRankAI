# Phase 4 Pass 2 — DB Priority and Command Speed

Date: 2026-07-15

Accepted canonical checkpoint: `3a0dad6a47065cf94aa2f36fe486fd06b48a7243` (`fix-2`)

Scope: Phase 4 Pass 2 only; Pass 3 delivery-idempotency work was not started.

## Outcome

Pass 2 is implemented and its automated exit gate is satisfied. Database work now enters one of four explicit priority classes with bounded admission, foreground reservations, lower-priority shedding, per-class metrics, role-aware connection labels, and cancellation-safe acquisition. Telegram commands acknowledge before audit/database work, command audits no longer block handlers, and `/signals` returns a bounded cached response when its live interactive read cannot acquire capacity.

No database schema, migration, dependency, payment, entitlement, execution, signal-validation, delivery-idempotency, or deployment-manifest change was made.

## Implemented contracts

### Four database priorities

`db/priority.py` defines the canonical `DBPriority` values:

| Priority | Admission contract | Default acquisition budget |
|---|---|---:|
| `INTERACTIVE` | Dedicated foreground lane for commands and callbacks | 750 ms |
| `CRITICAL` | Dedicated foreground lane for persistence, proof, and consequential mutations | 5 s |
| `BACKGROUND` | Bounded borrower; does not start while foreground work is active/waiting | 2 s |
| `ANALYTICS` | Zero shared-role reservation; nonblocking defer under pressure | 0 s |

On a two-connection shared role, interactive and critical work can occupy one lane each. Background work can borrow at most one slot only while foreground lanes are idle. Analytics is disabled/deferred on that shared budget unless the process is an explicit analytics role or the operator supplies the explicit shared-pool override.

The admission controller exposes, per class:

- current waiting and active counts;
- acquisition, timeout, dropped, deferred, and cancellation counts;
- cumulative wait time;
- cumulative transaction/session hold time;
- class limit, total capacity, and total active/waiting counts.

### Session API and compatibility

`db/session.py` now accepts:

```text
get_session(priority=DBPriority.INTERACTIVE)
```

The existing `interactive=True`, `critical=True`, and `noncritical=True` forms still map to the new classes and emit a warning once per legacy flag. Conflicting flags, or an explicit priority combined with a legacy flag, raise `ValueError` instead of silently changing durability semantics. Unclassified legacy sessions remain conservatively critical until their call sites move behind owning services in later passes.

Priority admission and the existing physical semaphores are both retained so current callers and pressure controls remain compatible. The effective session limit is clamped to the real pool size plus overflow, preventing an unsafe environment override from queuing work behind hidden SQLAlchemy capacity. Cancellation callbacks release a semaphore or priority permit if an executor thread completes after its awaiting task was cancelled.

`get_pool_diagnostics()` now reports the database role, application name, and full priority-admission snapshot. Connections default to:

```text
application_name=signalrankai/<role>
```

An explicit `DB_APP_NAME` remains supported. The role derives from `DB_ROLE`, then `RUN_MODE`, then the Railway service name.

### Command acknowledgement and degradation

`signalrank_telegram/command_resilience.py` adds:

- a thread-safe bounded TTL cache for command response payloads;
- callback acknowledgement or a bounded Telegram typing action before handler work;
- safe scheduling that consumes/logs background-task failures.

The active command wrapper in `signalrank_telegram/bot.py` now:

1. acknowledges first;
2. schedules command audit without awaiting it;
3. classifies that audit as deferrable analytics work;
4. executes the command under the existing bounded handler timeout and degraded error response.

The active `/signals` implementation now uses explicit interactive DB priority. Successful empty and populated indexes are cached with reconstructable button payloads. A DB admission/query timeout or other DB failure serves the recent cached index with a visible age/degraded notice; when no cache exists, the existing safe busy/error response remains.

The global callback router already acknowledged before route work and remains compatible.

## Test evidence

### Pre-change focused baseline

The initial DB/command regression selection completed with **25 passed and 1 inherited failure**. The failure was the existing Windows default-encoding error when a test reads UTF-8 `bot.py` using cp1252.

### Pass 2 focused verification

`tests/test_phase4_pass2_db_priority_and_command_speed.py` covers:

- a two-connection interactive/critical pressure scenario while analytics/background are deferred;
- end-to-end `get_session` pressure with fake sessions and physical semaphores;
- analytics-role idleness and borrower separation;
- synchronous and asynchronous cancellation without permit leakage;
- invalid API combinations and legacy mappings;
- exact timeout defaults, physical-cap clamping, role application naming, and transaction metrics;
- TTL expiry and bounded LRU eviction;
- callback ACK ordering and nonblocking command audit;
- `/signals` cached fallback during DB timeout.

Latest focused Pass 2 result: **12 passed**, 2 inherited deprecation warnings, in 4.82 seconds.

The widened DB/command selection completed with **37 passed and 1 inherited failure**. The one failure is the unchanged Windows cp1252 source-read error described above.

### Deterministic repository comparison

The canonical checkpoint was exported and run in an isolated directory using a sorted list of every otherwise collectable `tests/test_*.py` file. The known `test_broker_permission_validation.py` collection blocker was excluded equally from both runs.

Canonical checkpoint result: **435 passed, 31 failed, 2 errors**.

Final Pass 2 working-tree result: **447 passed, 31 failed, 2 errors**, 32 warnings, in 83.49 seconds. The 12 additional passes are the Pass 2 verification tests; the inherited failure/error counts are unchanged.

After that repository run, a metrics-only change added explicit deferred/timeout accounting for the physical-gate fallback path. Its focused verification completed with **22 passed**, 4 warnings, and source compilation passed; it does not alter admission or command behavior.

The 31 inherited failures remain in previously identified web/payment, readiness, DB-pool expectation, lifecycle/outcome mocks, encoding, and source-contract areas. The two errors are unchanged Windows ACL failures while pytest creates `tmp_path` fixtures.

### Exact collection and compilation

Exact collection found **480 tests and 1 collection error**. The inherited blocker remains:

```text
ImportError: cannot import name 'verify_api_key' from 'web.app'
```

The following source compilation completed successfully:

```text
python -m compileall -q core data db engine ml payments paystack services signalrank_telegram web
```

## Exit gate and limitations

Automated Pass 2 exit gate:

- four explicit DB priorities: **passed**
- interactive and critical progress under a two-slot pressure budget: **passed**
- analytics/background shedding under foreground pressure: **passed**
- bounded acquisition and physical capacity cap: **passed**
- cancellation without leaked capacity: **passed**
- role/class metrics and connection labeling: **passed**
- ACK before audit/database work: **passed**
- command audit does not delay the handler: **passed**
- cached/degraded interactive response: **passed**
- deterministic repository failure/error count increased: **No**

Operational DB saturation tests against a live staged PostgreSQL role and Telegram latency canaries are still required before production readiness. Full service-role deployment remains Pass 7 work. This pass does not claim launch readiness or start the durable delivery outbox/reconciliation work assigned to Pass 3.

Phase status:

- Phase 4: **in progress**
- Pass 1 — Signal Correctness and Live Validation: **complete**
- Pass 2 — DB Priority and Command Speed: **complete**
- Passes 3–10: **not started**
- Public production readiness: **No**
- Permitted next action after this report is finalized: **Phase 4 Pass 3 — Delivery Idempotency and Active-Message Reliability**
