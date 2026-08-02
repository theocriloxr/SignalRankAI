# SignalRankAI v1.3.6.8 — Performance Integrity Hotfix and 100,000+ User Architecture

Date: 2026-08-02
Release type: staging candidate
Production status: **blocked pending runtime certification**

## 1. Executive verdict

The uploaded v1.3.6.7 package already contains substantial signal, outcome, paper-trading, provider-health, delivery-proof and adaptive-learning systems. It is not an empty prototype. However, the observed `users_examined=6, failed_users=6` performance projection result is a release blocker, and the existing all-user sweep would not be safe or fair at 100,000+ users.

v1.3.6.8 repairs the immediate projection failure path and introduces scale-compatible contracts without prematurely enabling real execution or broad provider expansion.

This release does **not** claim that the complete v1.4–v2.0 ecosystem is already production-certified. The supplied expansion prompt explicitly requires the baseline performance, deduplication, notification, paper-trading and Telegram runtime gates to pass before broad provider activation. The work is therefore split into:

1. code that is safe and necessary now;
2. architecture foundations that are present but disabled;
3. later phases that remain gated by runtime evidence, legal availability, provider credentials, licensed data and sandbox/testnet certification.

## 2. Immediate defect: root cause and correction

### 2.1 Confirmed defects in v1.3.6.7

The previous `reconcile_all_performance_ledgers` implementation:

- selected the same first bounded set of users on every cycle;
- processed all users inside one shared transaction;
- caught each exception without logging the user, error class, stage or traceback;
- returned only a failure counter;
- did not isolate a failed user with a savepoint;
- could roll back successful partial-exit repair work when the outer iteration failed.

A second defect was identified in the policy migration path. Migration 0031 protects finalized performance rows with `trg_performance_ledger_finality`. The v1.3.6.7 upsert attempted to change finalized rows created under an older accounting policy without changing `corrected_at`, `corrected_by` and `correction_reason`. PostgreSQL therefore had grounds to reject every affected user. This is the most likely explanation for the six-of-six failure, though staging logs must confirm the exact exception.

### 2.2 v1.3.6.8 correction

The corrected projection now:

- uses `session.begin_nested()` for every user;
- logs reconciliation ID, Telegram user ID, internal user ID, error code, exception type, sanitized message, processing stage and transaction state;
- groups failures into `constraint_violation`, `invalid_data`, `transaction_aborted`, `missing_delivery_timestamp` and `unexpected`;
- raises an explicit certification failure when every examined user fails;
- commits verified outcome/partial-exit repairs before surfacing an all-user performance failure;
- uses a stable internal-user cursor stored in shared runtime state;
- processes bounded pages and continues from the last internal user ID;
- supports reset, no-wrap and dry-run modes;
- persists failed-user retry state and dead-letter evidence only after the database commit;
- aligns confirmed-delivery timestamp fallback across population selection and per-user projection;
- computes coverage from distinct user-signal delivery scopes, not delivery attempts;
- streams a canonical outcome-to-ledger mismatch audit and blocks health when any mismatch remains;
- preserves explicit human corrections;
- changes old finalized policy rows through an attributed system correction;
- appends `PerformanceCorrectionAudit` evidence for every systemic finalized-row migration;
- keeps the database finality trigger active rather than bypassing it.

No schema migration is required because the required correction and audit columns already exist.

## 3. New owner operations

### `/performance_rebuild dry_run`

Runs one bounded batch from the beginning without persisting ledger changes or advancing the production cursor. Use this first.

### `/performance_rebuild apply`

Runs one bounded batch from the beginning, commits valid rows and saves the cursor. The worker subsequently continues cursor-based processing.

### `/performance_rebuild status`

Shows the latest structured reconciliation result and ledger health.

### `/performance_audit [days]`

Checks proof-backed delivery count, ledger rows, missing rows, projection coverage and malformed terminal rows.

These commands require the strict configured owner identity, not a temporary owner bypass.

## 4. 100,000+ user target

### 4.1 Capacity envelope

The target should be planned around at least:

| Dimension | Initial large-scale design target |
|---|---:|
| Registered users | 100,000–500,000 |
| Concurrent active users | 20,000–100,000 |
| Connected broker/exchange accounts | 50,000+ |
| Canonical signals/day | 10,000–100,000 |
| User-visible alerts/day | 10–50 million peak-dependent |
| Outcome/lifecycle events/day | 1–20 million |
| Market events/day | billions if raw ticks/order books are retained |
| Webhook acknowledgement | p95 < 500 ms; p99 < 1 s |
| Qualified-signal delivery | p95 < 5 s |
| Notification queue age | p99 < 60 s |
| Projection coverage | target >= 99.9% |
| Duplicate user-visible deliveries | 0 |
| Duplicate live orders | 0 |

These are engineering targets, not measured current capacity. The platform must pass repeatable load tests before any such capacity is advertised.

### 4.2 Target service topology

```text
Telegram / Web / Mobile / Public API
                  |
       Edge admission + authentication
                  |
      Command/API service (fast ACK only)
                  |
       Durable command and event streams
          /        |         |        \
 Market-data   Signal/risk  Fan-out   Execution
 services      services     services  services
     |              |           |          |
 Provider      Canonical      Rate-aware   Venue
 gateways      event log      delivery     adapters
     |              |           |          |
     +---------- PostgreSQL transactional truth --------+
                     |              |
               Read models       Audit/ledger
                     |
        Analytics/time-series/object storage
```

Service ownership must remain explicit. Scheduler leases are not a substitute for partitioned queue ownership.

## 5. Durable event architecture foundation

`core/durable_event_stream.py` adds a disabled-by-default Redis Streams transport with:

- immutable, versioned `EventEnvelope`;
- event, correlation and causation IDs;
- tenant, user, account and signal ownership fields;
- idempotency key;
- deterministic partitioning;
- consumer-group creation;
- at-least-once reads;
- explicit acknowledgement;
- stale-message reclamation with `XAUTOCLAIM`;
- dead-letter streams;
- bounded retention;
- strict feature flag.

Ordering is promised only within the same partition key. Consumers remain responsible for idempotent side effects. The existing event bus is not replaced in this hotfix because doing so before a soak test would create an unnecessary release risk.

### Required future event families

- signal generated/rejected/reserved/delivered/delivery failed;
- entry triggered and lifecycle transitions;
- TP1/TP2/TP3, stop, partial exit and time stop;
- paper position/order/fill transitions;
- live order submitted/acknowledged/partially filled/filled/rejected/cancelled;
- reconciliation results;
- subscription/payment/entitlement transitions;
- model promotion/rollback/drift;
- provider quarantine/recovery;
- kill-switch transitions.

Each read model must maintain its own checkpoint and replay semantics.

## 6. Large-scale reconciliation design

Every population-wide job must use:

```text
cursor page -> partitioned work -> per-record savepoint
-> idempotent write -> checkpoint -> retry/backoff
-> poison isolation -> DLQ -> replay tooling
```

Non-negotiable rules:

- no unbounded `SELECT * FROM users`;
- no large offset pagination;
- no single transaction for the population;
- no silent exception counters;
- no destructive backfill;
- no retry loop without a terminal DLQ state;
- no full-population rebuild in a Telegram request;
- every backfill has a rate limit and pause switch.

v1.3.6.8 applies this pattern to performance reconciliation. Other global loops must be migrated in later releases.

## 7. Database scale plan

### 7.1 PostgreSQL remains transactional truth

Keep in PostgreSQL:

- users, organizations, accounts and entitlements;
- canonical signals and delivery proofs;
- lifecycle/outcome projections;
- financial ledger, orders, fills and positions;
- audit records, provider/account configuration and operational checkpoints.

Do not keep unlimited raw ticks, L2/L3 books, raw news payloads or model training corpora in the primary transactional database.

### 7.2 Partition candidates

Evaluate declarative range partitioning, and where justified sub-partitioning, for:

- signal lifecycle events;
- signal deliveries and attempts;
- outcomes and notification attempts;
- order/fill events;
- provider telemetry;
- audit events;
- ML features/predictions;
- market candles if retained in PostgreSQL.

Partition only after query-profile and migration rehearsal. Poor partition keys can make operations worse.

### 7.3 Required database controls

- PgBouncer-compatible connection policy;
- background/interactive pool separation;
- per-query and per-job timeouts;
- online index creation;
- expand/migrate/contract schema changes;
- vacuum, bloat and index-use monitoring;
- PITR and restore exercises;
- read replicas for dashboards/analytics;
- logical replication or CDC for downstream read models;
- retention/archive policies;
- immutable correction evidence;
- decimal-safe money, quantity and price types in all financial paths.

## 8. Notification and fan-out architecture

A canonical signal must not directly loop over all recipients.

```text
canonical signal
-> audience/entitlement snapshot
-> sharded recipient reservations
-> priority queues
-> Telegram/web/push workers
-> provider response
-> durable delivery proof
```

Required controls:

- global and per-chat rate limiting;
- `retry_after` handling;
- bounded concurrency and backpressure;
- quiet-hour scheduling without data loss;
- message-template versioning;
- blocked/deleted chat handling;
- priority classes;
- idempotent logical delivery;
- DLQ and replay;
- delivery lag, queue age and flood-limit metrics;
- no cooldown created until durable send confirmation exists.

The webhook must acknowledge and enqueue slow work; it must not perform expensive database/provider operations inline.

## 9. Provider architecture foundation

`data/provider_contracts.py` adds formal contracts for:

- `InstrumentDiscoveryProvider`;
- `MarketDataProvider`;
- `LiveQuoteProvider`;
- `OrderBookProvider`;
- `DerivativesDataProvider`;
- `NewsProvider`;
- `MacroDataProvider`;
- `OnChainDataProvider`;
- `ExecutionVenue`;
- `BrokerAccountProvider`;
- `PositionReconciliationProvider`;
- `CorporateActionsProvider`;
- `EconomicCalendarProvider`.

It also adds:

- canonical asset classes and instrument kinds;
- canonical instrument IDs;
- typed capabilities;
- typed unsupported-capability results;
- explicit certification states;
- separation between declared capability and production-certified capability.

This foundation is not an execution connector and makes no claim that any venue is live-certified.

### 9.1 Priority capability matrix

| Provider/venue | Principal use | Integration priority | Mandatory gate |
|---|---|---:|---|
| Existing configured providers | Stabilize current data coverage | A0 | current runtime certification |
| Hyperliquid | spot/perpetual data and testnet execution | A1 | key isolation, nonce/idempotency, testnet suite |
| Kraken | spot/futures, WebSocket/FIX, order-book quality | A1 | sandbox/account certification |
| dYdX | decentralized perpetual data/trading | A1 | chain/indexer/reconciliation tests |
| OANDA | FX/CFD practice and streaming | A2 | region and practice-account review |
| Alpaca | equity/options/crypto paper/live | A2 | paper certification and entitlement review |
| Interactive Brokers | multi-asset brokerage | A2 | market-data subscription and paper certification |
| Tradier | equities/options sandbox | A3 | options/conditional-order certification |
| Polygon/other licensed feeds | independent market/reference data | A2 | licensing and redistribution controls |
| DeFi routers | AMM/CLOB quote and execution routing | A4 | simulation, chain finality, wallet isolation |

Official documentation reviewed for this plan includes Hyperliquid exchange/info APIs, dYdX integration documentation, Kraken REST/WebSocket/FIX documentation, PostgreSQL, Redis Streams, Telegram Bot API, Railway, OpenTelemetry, OWASP and NIST AI RMF. Every connector must re-check current official documentation at implementation time.

### 9.2 Provider correctness rules

- online metadata discovery; no hidden static production universe;
- canonical symbol mapping and aliases;
- tick/step/min-notional checks;
- spot, margin, perpetual, dated future, option and CFD distinctions;
- base/quote/collateral and contract multiplier normalization;
- mark/index/last/mid price identity;
- source and receive timestamps;
- sequence/checksum/gap handling for books;
- provider-specific circuit breaker and rate budget;
- typed unsupported results;
- no cross-provider candle stitching unless a validated policy allows it;
- no free Yahoo/yfinance data as production-authoritative execution truth;
- data-only and execution support shown separately;
- jurisdiction and licensing restrictions recorded.

## 10. Order, position and financial integrity

### 10.1 Canonical order state machine

```text
CREATED -> RESERVED -> SUBMITTING -> ACKNOWLEDGED
        -> PARTIALLY_FILLED -> FILLED
        -> CANCELLING -> CANCELLED
```

Terminal/exception states:

```text
REJECTED | EXPIRED | FAILED | RECONCILIATION_REQUIRED | UNKNOWN_AT_VENUE
```

An HTTP 200 response is never execution proof. Store client order ID, venue order ID, individual fills, cumulative/remaining quantity, average fill, fees, amendments, child TP/SL orders, position/margin mode, leverage and reconciliation time.

### 10.2 One portfolio-risk authority

Paper, live and copy trading must use the same risk authority for:

- gross/net exposure;
- asset, currency, sector and correlated exposure;
- open risk and margin utilization;
- liquidation distance;
- concentration and maximum positions;
- daily/rolling drawdown;
- volatility/correlation-aware sizing;
- stale data, spread, slippage and provider breakers;
- per-user/account/global kill switches.

Reservation and risk checks must be atomic.

### 10.3 Financial ledger

All monetary and paper-cash changes must originate from append-only entries with correction postings, not dashboard rewrites. Reconcile deposits, subscriptions, credits, reserved margin, fills, fees, funding, rebates, realized P&L, refunds, referral commissions and payouts. Use double-entry principles wherever real money is represented.

## 11. Multi-tenant and API security

Every protected object must carry and enforce appropriate ownership:

- organization ID;
- user ID;
- broker account ID;
- strategy ID;
- subscription/entitlement ID.

Required controls:

- tenant-aware SQL, cache and stream keys;
- object-level and function-level authorization;
- per-tenant quotas and rate limits;
- read-only/trading/admin credential separation;
- encrypted broker credentials and dedicated secret manager;
- withdrawal permission rejection where detectable;
- IP allowlisting guidance;
- webhook signature and replay protection;
- audit of every privileged action;
- dependency/container/secret scanning;
- safe support impersonation with reason and audit;
- privacy export/deletion workflows;
- emergency provider, execution and global kill switches.

Threats explicitly covered include broken object authorization, broken authentication, unrestricted resource consumption, unsafe third-party API consumption, credential theft, replay, duplicate orders, queue poisoning, provider compromise, market-data manipulation and insider misuse.

## 12. Adaptive AI and strategy governance

The adaptive engine must learn from full sequences and retain provenance, but no model may directly alter live risk without governance.

Required lifecycle:

```text
dataset/version -> leakage tests -> train -> held-out evaluation
-> calibration -> shadow/challenger -> approval -> limited rollout
-> drift monitoring -> rollback
```

Maintain feature/label registries, model and strategy cards, training lineage, asset/regime slices, uncertainty estimates, calibration curves, drift thresholds and reproducible environments. An uncalibrated score must not be displayed as probability. Public performance and model claims remain disabled until statistically defensible certification passes.

## 13. Product, entitlement and operations gaps

The long-term ecosystem still requires separately deployable services for:

- web/mobile dashboard and account management;
- smart terminal;
- DCA/grid/rebalancing/TradingView bots;
- market-making and arbitrage families with separate suitability gates;
- strategy SDK, visual builder, backtesting, walk-forward and Monte Carlo;
- copy trading with follower-specific risk and audit;
- subscriptions, receipts, proration, retries, disputes and Paystack reconciliation;
- referral/affiliate accounting;
- admin/support console, incident banners and status page;
- product funnel, retention, cost and reliability analytics;
- exports and tax-compatible records where feasible.

These are roadmap items, not silently enabled by this hotfix.

## 14. Observability and service-level objectives

Every signal/order must be traceable by correlation IDs across market data, strategy, ML, risk, deduplication, persistence, fan-out, delivery, entry, outcome, performance and notification.

Required metrics include:

- webhook p50/p95/p99;
- signal persistence and delivery latency;
- queue lag/age and DLQ count;
- database pool saturation and slow queries;
- scheduler/partition ownership;
- provider latency, source age, rate budget, breaker and reconnects;
- sequence gaps and stale data;
- order acknowledgement/fill/reconciliation latency;
- slippage and fees;
- projection coverage/mismatch/malformed rows;
- dedup rejections and duplicate-delivery/order invariants;
- model version, calibration and drift;
- infrastructure/provider cost per active user and delivered signal.

OpenTelemetry should provide common trace, metric and log context. Each alert needs an owner, threshold, runbook and automatic safety action.

## 15. Release engineering and Railway

At 100,000+ users, replicas alone do not make stateful jobs safe. Every replica-sensitive service must use queue partitioning or leases and idempotency.

Required release controls:

- immutable release manifest and exact commit gate;
- dependency lock and SBOM;
- signed/reproducible artifact where feasible;
- feature/provider/user allowlist flags;
- shadow and canary rollouts;
- expand/contract migrations;
- health checks before traffic;
- automatic rollback criteria;
- environment drift detection;
- multi-region and disaster-recovery exercises;
- read-only emergency mode.

Railway supports replicas and multi-region routing, but database, Redis, worker ownership and external-provider limits remain application responsibilities.

## 16. v1.3.6.8 staging procedure

1. Keep all live/copy/public-marketing switches off.
2. Deploy the same artifact to front door, engine and worker.
3. Set `APP_VERSION=1.3.6.8` and exact `EXPECTED_RELEASE_COMMIT` after committing.
4. Keep `DURABLE_EVENT_STREAM_ENABLED=0` and all new execution provider flags off.
5. Confirm all services log the same version, SHA, migration head and role.
6. Run `/performance_rebuild dry_run`.
7. Inspect grouped errors. Any nonzero error must have a user ID, type, traceback and reason.
8. Run `/performance_rebuild apply`.
9. Allow the worker cursor to continue through the full eligible population.
10. Run `/performance_rebuild status` and `/performance_audit 365`.
11. Run controlled duplicate-thesis, failed-delivery and four-hour cooldown tests.
12. Exercise paper reset/open/reject-same-asset/force-close/restart reconciliation.
13. Test every Telegram command and inline callback; measure webhook p95/p99.
14. Soak for at least 24 hours with representative provider outages and queue pressure.
15. Do not enable production until the certification checklist passes.

## 17. Required log evidence for deploy/no-deploy review

Provide logs containing:

- version banner from all services;
- migration head and service role ownership;
- one complete performance reconciliation result;
- `failed_users=0` or every failure fully diagnosed and corrected;
- failure-reason map;
- cursor progression and full sweep completion;
- projection coverage, missing rows and malformed terminal rows;
- `/performance` output showing TP1/TP2 stopped buckets when evidence exists;
- controlled concurrent duplicate test with one canonical stored signal;
- four-hour same-user asset suppression;
- proof that failed send does not set cooldown;
- notification queue pending/delivered/failed/DLQ counts;
- quiet-hour queue survival;
- paper position lifecycle and restart reconciliation;
- webhook and delivery latency percentiles;
- database pool and slow-query metrics;
- provider failover/source-age evidence;
- no live order, copy-trade or public-return switch enabled.

## 18. Certification gates

### Gate A — performance integrity

- all eligible users eventually processed;
- failed users = 0;
- projection coverage >= 99% for the current prompt gate, with an operational target of 99.9%;
- malformed terminal rows = 0;
- outcome-to-ledger mismatch = 0;
- human corrections preserved;
- every systemic correction has an audit row.

### Gate B — deduplication

- one stored canonical thesis under concurrent generation;
- BUY/LONG and SELL/SHORT normalize;
- negligible repricing/timeframe variants are suppressed by policy;
- no owner/admin bypass;
- same user/asset four-hour lock;
- failed sends do not create a sent lock.

### Gate C — notification and Telegram

- no budget-exhaustion loop;
- terminal messages complete and traceable;
- exactly-once logical queue exit;
- immediate callback acknowledgement;
- webhook p95/p99 SLO met.

### Gate D — paper trading

- reset/force close/open/reject duplicate/restart reconcile;
- fees/spread/slippage included;
- exposure, daily loss and aggregate risk enforced.

### Gate E — release safety

- exact artifact/commit on all services;
- rollback rehearsed;
- no live/copy/public switches;
- 24-hour soak passes.

## 19. Rollback

Application rollback is safe because v1.3.6.8 adds no schema migration. To roll back:

1. keep execution and public claims disabled;
2. deploy the exact previous v1.3.6.7 artifact;
3. preserve `performance_correction_audit` and corrected ledger rows—do not destructively reverse them;
4. inspect whether any policy corrections require a new attributed correction rather than direct mutation;
5. reset the reconciliation cursor only after operator review;
6. verify outcome, paper and notification queues before resuming normal staging traffic.

## 20. Remaining risk register

| Risk | Current treatment | Release effect |
|---|---|---|
| Exact six-user exception not yet observed after patch | detailed diagnostics added | production blocked until logs confirm |
| Semantic dedup not runtime-proven | controlled test required | production blocked |
| Telegram latency previously high | SLO and queue-path test required | production blocked if p99 >= 1 s |
| Paystack key pair incomplete | recovery remains disabled | billing scale blocked |
| XAGUSD live quote gaps | capability-aware fail closed | asset remains uncertified |
| Event-stream foundation not integrated | disabled flag | no current behavior change |
| Provider contracts not connectors | explicit certification states | no false support claim |
| 100k capacity not load-tested | capacity plan and test requirement | no scale claim allowed |
| Legal/licensing review incomplete | jurisdiction/licensing gate | marketplace/copy/live expansion blocked |
| Railway single-provider concentration | DR/multi-region plan required | business continuity risk remains |

## 21. Official research references

- PostgreSQL table partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- PostgreSQL logical replication: https://www.postgresql.org/docs/current/logical-replication.html
- Redis Streams and consumer groups: https://redis.io/docs/latest/develop/data-types/streams/
- Redis XAUTOCLAIM: https://redis.io/docs/latest/commands/xautoclaim/
- Telegram Bot API: https://core.telegram.org/bots/api
- OpenTelemetry: https://opentelemetry.io/docs/
- OWASP API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- NIST AI RMF: https://www.nist.gov/itl/ai-risk-management-framework
- Railway scaling: https://docs.railway.com/deployments/scaling
- Railway multi-region failover guide: https://docs.railway.com/guides/multi-region-api-failover
- Hyperliquid exchange endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
- Hyperliquid info endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- dYdX developer documentation: https://docs.dydx.xyz/
- Kraken API documentation: https://docs.kraken.com/api/

## 22. Definition of done for the overall programme

The complete programme is done only when every claimed provider/capability is independently certified; live execution is auditable and idempotent; copy trading is consented and reconciled; public performance is statistically defensible; 100,000+ load profiles pass with recovery tests; security/legal/licensing reviews are closed; RPO/RTO exercises pass; and every release is reversible without losing financial or audit truth.
