# SIGNALRANKAI V7 — MAXIMUM-COMPLETENESS, CLEAN-SLATE, PRODUCTION-GRADE, FULL-ECOSYSTEM MASTER BUILD PROMPT

**Generation date:** 2026-07-27  
**Supersedes:** the V6 control layer where the two conflict; the complete V6 prompt is preserved verbatim later in this document and remains binding wherever V7 is silent.  
**Input V6 SHA-256:** `b9baec0fe435f16babeba06cbbba802976541519d26118d36865ef8ec6f50a8e`  
**Primary product:** SignalRankAI — a Telegram-first, multi-user, multi-asset trading-intelligence ecosystem with deterministic analysis, optional AI/ML review, proof-backed delivery, complete lifecycle and outcome tracking, paper/shadow/backtest/walk-forward separation, subscriptions/payments readiness, and independently gated broker execution.  
**Initial deployment target:** Railway; one application replica; one Uvicorn worker; PostgreSQL behind PgBouncer transaction pooling; physically separate RedisState and RedisDelivery services; Telegram webhook mode; engine and advanced features activated only through staged evidence gates.

---

# V7 CONTROL LAYER — READ THIS BEFORE THE PRESERVED V6 PROMPT

This V7 control layer is the highest-priority build contract after the owner’s latest explicit instruction. It expands V6 without deleting any V6 requirement. The implementation agent must process this entire document, the supplied source archive, logs, reports, patches, database state, and current official integration documentation as one requirement corpus.

The requested outcome is not a long analysis, architecture proposal, or code sample. The outcome is a complete, coherent repository, migrations, tests, diagnostics, operational evidence, deployment configuration, documentation, and release package that can be built, migrated, deployed, exercised, diagnosed, and maintained without hidden gaps.

No natural-language prompt can guarantee zero defects. The binding interpretation of “no gaps, mistakes, broken flows, or incomplete code” is:

1. every requirement and legacy behaviour is discovered and given an explicit disposition;
2. every enabled path has a formal contract, implementation, test, runtime diagnostic, and evidence requirement;
3. unsupported, unverified, dangerous, or externally blocked paths remain unavailable by policy rather than appearing to work;
4. every failure is observable, attributable, retryable or terminal by explicit policy, and recoverable where recovery is valid;
5. completion language is restricted to evidence-backed verdicts.

---

# V7-0. NON-NEGOTIABLE EXECUTION BEHAVIOUR

Act as the principal product architect, staff Python/backend engineer, quantitative engineer, database/PgBouncer engineer, distributed-systems engineer, Telegram platform engineer, payments engineer, broker-integration engineer, ML/platform engineer, SRE, security engineer, test architect, release manager, technical writer, and incident commander.

You must continue from discovery through implementation and verification. Do not stop after producing a plan. Do not leave placeholder handlers, `pass`, `TODO`, commented-out production branches, fake provider responses, test-only implementations wired into production, disabled commands without a documented product decision, or migration scripts that only work on an empty database.

Use Git from the first modification. Create small reviewable commits grouped by verified vertical slice. Before every destructive or irreversible action, create a checkpoint and record the rollback method. At every context or execution limit, persist a resumable checkpoint containing:

- exact repository path and commit;
- completed requirement IDs;
- failing tests and full commands;
- open blockers;
- changed files;
- migration state;
- next deterministic action;
- generated artefact paths and checksums.

Never rely on conversational memory as the sole project record. Store decisions, mappings, test results, and blockers in version-controlled machine-readable files.

Do not rewrite good working code merely for style. Do rewrite code when required to eliminate unsafe architecture, duplicated truth, hidden coupling, PgBouncer incompatibility, untestable side effects, incorrect market semantics, or unprovable behaviour.

---

# V7-1. INPUT CORPUS, TRUST BOUNDARIES, AND SOURCE PRECEDENCE

## V7-1.1 Required inputs

Materialise and hash every supplied input:

- latest SignalRankAI source archive;
- all patches and release ZIPs;
- V7 and preserved V6 prompt;
- historical V5/V4 specifications;
- project documents, TODOs, registers, ledgers, runbooks, scorecards and proof manifests;
- Railway deployment logs;
- Telegram command/button failure logs;
- database migration failures and schema-drift evidence;
- provider, Gemini, Paystack, TradingView and MetaApi evidence;
- owner decisions from cross-chat reconstruction;
- current official documentation for every external dependency.

Treat archives, logs, prompts, database content, provider payloads, Telegram updates, webhook bodies, user data, generated AI output, and imported configuration as untrusted input until validated.

## V7-1.2 Precedence

Apply this order:

1. latest explicit owner instruction;
2. this V7 control layer;
3. preserved V6 prompt;
4. binding cross-chat decision ledger and universal requirement register;
5. latest source archive and tests as forensic behavioural evidence;
6. latest runtime logs and live database evidence;
7. historical prompts/documents;
8. old code and comments.

A passing old test does not override a newer business rule. A runtime log does not prove intended behaviour, but it does prove what occurred. A comment does not override executable behaviour. A provider response does not override canonical asset classification.

## V7-1.3 Conflict handling

For every conflict create a record with:

- conflict ID;
- sources and exact locations;
- old and new interpretations;
- user impact;
- data-migration impact;
- security/financial impact;
- selected decision and authority;
- compatibility/deprecation plan;
- tests and evidence required.

Never silently choose a price, threshold, tier entitlement, retention period, jurisdictional rule, provider entitlement, or execution permission.

---

# V7-2. MACHINE-READABLE REQUIREMENTS AND TRACEABILITY

Create these version-controlled artefacts before major implementation:

```text
requirements/
  requirements.yaml
  decisions.yaml
  conflicts.yaml
  incidents.yaml
  blockers.yaml
  feature_flags.yaml
  environment_registry.yaml
  command_registry.yaml
  callback_registry.yaml
  provider_registry.yaml
  release_gates.yaml
  evidence_catalogue.yaml
  legacy_disposition.json
```

Every requirement must have:

- stable ID such as `SRA-DB-001`;
- title and full statement;
- source references;
- priority: `P0`, `P1`, `P2`, `P3`;
- release phase;
- owner/domain;
- safety classification;
- enabled/disabled policy;
- implementation modules;
- migrations/data impact;
- test IDs;
- runtime diagnostic IDs;
- evidence type;
- status: `UNASSESSED`, `DESIGNED`, `IMPLEMENTED`, `TESTED_LOCAL`, `PROVEN_STAGING`, `PROVEN_LIVE`, `BLOCKED_EXTERNAL`, `DISABLED_BY_POLICY`, `RETIRED_APPROVED`;
- acceptance criteria written as observable facts;
- rollback/deactivation procedure.

Generate a traceability report proving:

```text
source requirement
→ decision
→ design/ADR
→ code
→ schema/event/API contract
→ tests
→ runtime metric/diagnostic
→ deployment phase
→ evidence
→ verdict
```

A requirement cannot be marked complete merely because code exists. Unknown requirements block the strongest verdict.

---

# V7-3. PRODUCT BOUNDARIES AND RELEASE LINES

SignalRankAI contains separately releasable products:

1. deterministic advisory signal generation;
2. Telegram delivery and user experience;
3. proof-backed lifecycle/outcome tracking;
4. portfolio/performance reporting;
5. paper trading;
6. shadow/rejected-candidate research;
7. deterministic replay/backtesting/walk-forward;
8. offline ML training and model governance;
9. Gemini advisory review/explanation;
10. TradingView alert ingestion;
11. Paystack subscriptions/receipts/referrals/support;
12. MetaApi demo execution;
13. copy trading;
14. Smart DCA;
15. real-money execution and payouts.

Each product line must have independent feature flags, entitlements, threat model, tests, diagnostics, activation gates, rollback, and verdict. Advisory readiness must not imply payment or execution readiness. Demo execution must not imply real execution readiness.

Real-money execution, copy trading, Smart DCA, public payments, real payouts, and automatic trading are disabled by default until separately approved and proven.

---

# V7-4. TARGET REPOSITORY AND MODULAR MONOLITH CONTRACT

Build a modular monolith that can later split into services without rewriting domain logic. Use Python 3.12+ only after dependency compatibility is proven; otherwise pin the exact supported Python version. Prefer a `src/` layout and `pyproject.toml` with a fully locked dependency graph.

Required bounded contexts:

- identity and users;
- terms/privacy/preferences;
- tiers, subscriptions and entitlements;
- instruments and asset taxonomy;
- market data and provider capabilities;
- strategies and features;
- signal decisions and scoring;
- risk and exposure;
- delivery and Telegram;
- lifecycle and outcomes;
- portfolio/performance;
- paper/shadow/replay/backtest/walk-forward;
- news/macro/on-chain;
- ML telemetry/models;
- payments/receipts/referrals/support;
- broker accounts/execution/reconciliation;
- audit/security/operations.

Required port types include repositories, unit of work, clock, ID generator, market-data providers, news providers, AI reviewer, Telegram transport, delivery queue, state cache, payment gateway, broker gateway, encryption/KMS adapter, audit sink, metrics/tracing, feature flags, and notification transport.

Domain code must not import FastAPI, SQLAlchemy, Redis, Telegram SDKs, Paystack, MetaApi, Gemini, Railway, or provider clients.

Create architecture tests that fail when forbidden imports or dependency directions appear.

---

# V7-5. FORMAL DOMAIN TYPES, NUMERIC SAFETY, AND TIME

## V7-5.1 Strong identifiers

Use typed IDs for user, signal, candidate, delivery, lifecycle event, outcome, payment, receipt, broker account, execution intent, order, position, provider request, audit event, command execution, callback token, and correlation/trace IDs. Never interchange raw integers/UUIDs across domains without explicit conversion.

## V7-5.2 Money and prices

- Never use binary floating point for money, account balances, fees, subscription amounts, P&L ledger values, risk capital, or broker sizing decisions.
- Use integer minor units for payment gateways and `Decimal`/PostgreSQL `NUMERIC` for financial calculations.
- Store currency code with every money value.
- Paystack requests must use the provider-required currency subunit; NGN policy must correctly represent kobo.
- Define rounding mode explicitly for price precision, tick size, quantity step, fees, P&L and percentage display.
- Position sizing rounds down to avoid increasing risk.
- Never promote an invalid calculated size to a broker minimum without recalculating and proving risk remains within limit.
- Persist raw provider values and canonical normalised values where audit requires both.

## V7-5.3 Time

- Persist timezone-aware UTC timestamps.
- Use monotonic clocks for durations, timeouts, retry timing and latency.
- Keep wall-clock and monotonic concepts separate.
- Persist provider event time, exchange time, receive time, processing time and user-display timezone.
- Validate clock skew and out-of-order events.
- Use explicit exchange calendars and DST handling.
- No `datetime.utcnow()` or naive production timestamp.

## V7-5.4 Percentages and returns

Define whether every percentage is decimal fraction or percentage points. Store reward/risk and R-multiple independently. Specify inclusive/exclusive boundaries for TP/SL touches and gap-through behaviour. Property-test sign, direction, and rounding semantics.

---

# V7-6. EVENT, API, DATABASE, AND MESSAGE CONTRACT VERSIONING

Every durable event, queue message, webhook payload, callback payload, API response, audit record, model feature row and export file must include a schema version.

Create a schema catalogue with:

- owner;
- JSON/Pydantic/Avro-equivalent schema;
- compatibility mode;
- required/optional fields;
- sensitive fields;
- idempotency key;
- producer and consumers;
- retention;
- migration/upcaster;
- deprecation date;
- tests.

Backward-compatible readers must tolerate additive fields. Breaking changes require a new version and migration/upcaster. Unknown versions must fail safely and enter a diagnosable dead-letter path rather than being misinterpreted.

HTTP APIs use explicit versioning. Telegram callback payloads use compact versioned codecs. Database rows containing state machines persist state-machine version. ML exports persist feature-schema version and code/data hashes.

---

# V7-7. CONSISTENCY, IDEMPOTENCY, OUTBOX/INBOX, AND SAGAS

Use PostgreSQL as durable truth and explicit application-level idempotency for at-least-once transports.

Implement transactional outbox/inbox patterns for operations that combine database changes with Telegram, Redis Streams, Paystack, TradingView, Gemini, or broker I/O.

Required invariants:

- database state and an outbound intent are committed atomically;
- network I/O never occurs inside the database transaction;
- workers claim intents with bounded leases/versioning;
- every external call has a stable idempotency key where supported;
- uncertain external results enter reconciliation, not blind retry;
- successful effects are recorded with provider identifiers and payload hashes;
- inbox tables reject replayed external events;
- retries are bounded and classified;
- dead letters remain visible and recoverable;
- administrative replay is authorised, audited and idempotent.

Define sagas for:

- signal reservation → Telegram send → proof persistence;
- payment initialise → webhook/verify → entitlement → receipt;
- execution reservation → broker order → acknowledgement → reconciliation;
- refund/reversal → entitlement correction → receipt/audit;
- command mutation → durable result → Telegram reply.

No code may implement “exactly once delivery” as a claim about the network. The requirement is exactly-once business intent through idempotency, durable evidence and reconciliation.

---

# V7-8. POSTGRESQL AND PGBOUNCER — EXACT PRODUCTION CONTRACT

The system must be designed specifically for PgBouncer transaction pooling.

## V7-8.1 Connection architecture

- one shared async SQLAlchemy engine per process;
- `NullPool` behind PgBouncer unless a measured, documented alternative is proven;
- no engine creation per event loop, thread, command, scheduler invocation or repository;
- no `AsyncSession` shared across tasks;
- no nested session unless reusing the current unit of work;
- explicit `DB_PGBOUNCER_MODE` and separate direct migration/admin URL where available;
- configure asyncpg prepared-statement behaviour according to the deployed PgBouncer version and server settings;
- test prepared-statement cache invalidation and DDL changes;
- set application name and bounded connect/command/statement/lock/idle-in-transaction timeouts;
- redact credentials in all logs.

## V7-8.2 Forbidden transaction-pooling assumptions

Do not depend on session-level `SET`, `LISTEN`, session advisory locks, prepared SQL created with `PREPARE`, preserved temporary tables, session variables, or connection affinity. Use transaction-scoped alternatives or another service.

## V7-8.3 Session ownership

Every session acquisition requires:

- non-empty operation label generated at the call site;
- priority;
- timeout;
- task/thread/loop identity;
- request/command/correlation ID;
- acquisition stack in diagnostics mode;
- cancellation-safe `finally` cleanup;
- rollback on any `BaseException`, including cancellation;
- close and admission-token release exactly once.

The session context manager must make it impossible to produce `unlabelled` holders. A missing label is a programming error in tests and a generated caller label in production diagnostics.

## V7-8.4 Admission policy

Maintain separate logical budgets for interactive commands, critical lifecycle/outcome work, background maintenance and analytics. Maintenance and analytics may be deferred. Interactive commands and outcome tracking may not starve each other. Do not simply raise the connection limit to hide a leaked transaction.

Record holder age. Warn at 5 seconds, fail diagnostics at 10 seconds, page at 30 seconds. Include current SQL/transaction state where safe, caller stack, and external await detection.

## V7-8.5 No network calls in transaction

Add runtime context tracking and tests that fail when Telegram/provider/Gemini/Paystack/MetaApi/Redis-blocking I/O is attempted while a DB unit of work is active.

## V7-8.6 Query discipline

- bounded pagination and deterministic ordering;
- no unbounded `SELECT *` on hot tables;
- no N+1 fan-out;
- required indexes justified by query plans;
- `EXPLAIN (ANALYZE, BUFFERS)` evidence on representative staging data;
- lock ordering documented;
- optimistic version/CAS or row locks for lifecycle transitions;
- transaction isolation selected per operation;
- serialisation/deadlock retries bounded and idempotent;
- no long transactions around batch computation.

## V7-8.7 Migration safety

Test:

1. empty DB to head;
2. every revision upgrade one-by-one;
3. representative legacy DB to head;
4. partial/stamped/drifted DB;
5. duplicate active theses;
6. pre-existing payment receipts;
7. missing columns/indexes/constraints;
8. large tables and lock duration;
9. rollback or forward-fix policy;
10. migration rerun/idempotency where deliberately supported.

Pre-deploy migration output must state start revision, target revision, duration, repaired rows, created objects and checks. Never delete financial or signal evidence to satisfy a constraint.

---

# V7-9. TELEGRAM COMMANDS, CALLBACKS, AND WEBHOOK RELIABILITY

The reported “commands are not working” failure is a P0 incident. Command operability must be proven, not inferred from handler count.

## V7-9.1 Webhook acceptance path

The HTTP webhook path performs only:

1. route/method/content-type/size validation;
2. constant-time secret-token validation;
3. JSON parsing and Telegram update schema validation;
4. update ID/idempotency metadata extraction;
5. durable append to RedisDelivery or explicitly configured bounded fallback;
6. immediate 2xx after durable acceptance.

It must never wait for PostgreSQL, a command handler, provider, Gemini, Paystack, MetaApi, scheduler or signal engine.

Every non-2xx response includes an internal reason code in structured logs, such as `INVALID_SECRET`, `MALFORMED_UPDATE`, `REDIS_DELIVERY_UNAVAILABLE`, `STREAM_APPEND_FAILED`, `BACKPRESSURE_REJECTED`, `APPLICATION_DRAINING`, or `PAYLOAD_TOO_LARGE`.

Telegram pending updates and last error are readiness/alert signals. Never use `drop_pending_updates=true` during normal deployment. Destructive pending-update removal requires explicit owner approval.

## V7-9.2 Command independence

Core commands must remain functional while the signal engine is paused, providers are degraded, Gemini is unavailable, payments are disabled, and broker execution is disabled. A command may return a precise degraded response, but it must not disappear or hang.

Reserve interactive DB capacity. Commands must not be blocked by outcome refresh, bulk keyboard updates, analytics, resend scanning or maintenance.

## V7-9.3 Command registry completeness

For every command and alias define:

- canonical name;
- aliases;
- description and help text;
- role/tier/profile requirement;
- terms requirement;
- feature flag;
- mutation/read-only class;
- rate limit;
- DB priority and maximum DB time;
- overall timeout;
- required external dependencies;
- degraded behaviour;
- audit event;
- reply template/schema;
- safe staging probe;
- deterministic fixtures;
- tests.

Generate BotFather command lists and `/help` from the registry. Compare runtime registration to the registry at startup. Refuse readiness when a required command is missing, duplicated, shadowed by group ordering, or mapped to a placeholder.

## V7-9.4 Handler pipeline

Every update gets correlation IDs and transitions:

```text
RECEIVED → DURABLY_QUEUED → CLAIMED → ROUTED → ACKNOWLEDGED
→ STARTED → REPLIED/EDITED → COMPLETED
```

Failure states include `REJECTED`, `TIMED_OUT`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`, and `DEAD_LETTERED`.

Persist or metric-record latency at each stage. A handler exception must produce a user-safe reply with reference ID unless Telegram itself is unavailable.

## V7-9.5 Callback contract

- ACK callback immediately, preferably before DB/network work;
- callback data must stay within current Telegram limits verified from official docs;
- compact opaque token rather than exposed database IDs where appropriate;
- ownership/entitlement/staleness/replay validation;
- one matching route only;
- idempotent mutation;
- version/upcaster policy;
- expired buttons return an explanatory replacement path;
- cross-user and forged-token tests;
- message edit and reply fallback when original message is unavailable.

## V7-9.6 Command certification harness

Build a staging-only command probe service or script that:

- uses a dedicated test bot/chat/user fixtures;
- sends or injects each safe command;
- waits for the expected response contract;
- records Telegram update/message IDs;
- exercises each inline button;
- verifies immediate callback ACK;
- validates DB effects and user isolation;
- restarts the app and retests persistence;
- classifies destructive/money/broker commands as manual-approved tests;
- emits HTML/Markdown/JSON matrix with `PASS`, `FAIL`, `BLOCKED`, `DISABLED_BY_POLICY`.

Handler registration count alone is never command proof.

## V7-9.7 Active message refresh

Read bounded immutable snapshots in a short DB transaction, close it, perform Telegram edits with bounded concurrency, then persist results in short transactions. Startup bulk refresh is disabled. One delayed bounded refresh may start only after webhook readiness and must yield to interactive commands/outcome tracking.

---

# V7-10. REDIS DELIVERY, BACKPRESSURE, AND RECOVERY

Use Redis Streams for durable work transport and PostgreSQL for business evidence.

Define stream names, message schemas, consumer groups, retention, maximum length policy, claim timeout, retry count, dead-letter stream and replay tooling.

Required message metadata:

- schema version;
- message/event ID;
- idempotency key;
- correlation/causation/trace IDs;
- created and expiry timestamps;
- attempt count;
- producer;
- target user/chat where applicable;
- payload hash;
- priority;
- sensitivity classification.

Consumers must use `XREADGROUP`, process, persist proof, then `XACK`. Monitor `XPENDING`; reclaim dead-consumer work with `XAUTOCLAIM`/equivalent. Never acknowledge before successful durable business processing.

Backpressure policy must specify:

- maximum queue age and depth;
- admission thresholds;
- low-priority shedding/deferment;
- user-facing degradation;
- retry-after behaviour;
- autoscaling constraints;
- circuit opening;
- recovery hysteresis.

RedisDelivery loss must not be treated as accepted delivery. RedisState loss must reconstruct without expiring or losing durable active signals.

Build queue inspection and safe replay commands with audit, dry-run, target filters and idempotency checks.

---

# V7-11. MARKET INSTRUMENT MASTER AND PROVIDER CERTIFICATION

Create a canonical instrument master. The same ticker text may represent different venues or market types; symbol strings alone are not identities.

Each instrument includes canonical ID, asset class, market type, venue, base/quote/settlement currencies, contract type, expiry, strike, option type, multiplier, inverse/linear flag, precision, tick/lot/notional rules, session calendar, timezone, provider mappings, broker mappings, real-time/delayed status, and provenance.

Provider adapters must return typed results and typed failures, never ambiguous `None`.

Failure taxonomy includes authentication, entitlement, region, rate limit, quota exhausted, timeout, transport, provider 5xx, invalid symbol, unsupported timeframe, market closed, empty response, malformed response, stale data, delayed data, data-quality failure and circuit-open.

Provider routing must consider capability, asset class, market type, timeframe, freshness, real-time entitlement, region, quota, latency, health and execution-truth eligibility. Never fallback across incompatible market types or silently replace an index with an ETF proxy.

REST is the initial correctness path. WebSockets are optional and disabled by default. Socket failures cannot imply total market-data blackout while certified REST data remains available. Enable sockets one provider at a time and reconcile bars/quotes against REST.

Certification requires:

- public/sandbox/live credential classification;
- representative instruments;
- market-open and market-closed tests;
- timestamp/freshness checks;
- rate-limit and circuit behaviour;
- invalid-symbol/timeframe tests;
- payload schema fixtures;
- independent sanity comparison where available;
- latency and delay disclosure;
- saved evidence with secret redaction.

An adapter is not production-supported until certified in the exact deployed environment and plan.

---

# V7-12. QUANTITATIVE CORRECTNESS AND RESEARCH GOVERNANCE

## V7-12.1 Deterministic first

Signal creation must be deterministic for a fixed input dataset, configuration and code version. Persist the dataset/provider/time window, feature version, strategy versions, configuration hash, and random seed where randomness is valid.

## V7-12.2 Indicator reference tests

For every indicator and derived feature:

- formal definition;
- warm-up/minimum periods;
- missing-data policy;
- price basis;
- numerical tolerance;
- comparison against at least one trusted reference implementation or independently calculated fixtures;
- property tests for invariants;
- edge cases for flat series, gaps, zeros, negative prices where valid, extreme volatility and short histories.

## V7-12.3 Strategy contract

Every strategy declares supported asset classes/market types/timeframes, prerequisites, setup, entry, invalidation, SL/TP generation, expected holding period, regime, failure reasons, version, and tests. Unsupported combinations are explicit, not silently skipped.

## V7-12.4 Anti-bias requirements

Backtest/replay/walk-forward must prevent look-ahead, target leakage, survivorship bias, universe hindsight, timestamp misalignment, revised-data leakage, selection bias and fee/slippage omission. Corporate actions, futures rolls and market calendars must be handled when relevant.

## V7-12.5 Score calibration

Store raw component scores and final score. Evaluate reliability with calibration curves, Brier score or suitable probabilistic metrics, expected calibration error, discrimination and sample size. Detect saturation and drift. Do not market nominal confidence as empirical probability without calibration evidence.

## V7-12.6 Outcome semantics

Wins count according to the owner-defined TP semantics; SL is a loss; missed entries and expiries remain explicit outcome classes and notify users where configured. Include spread/slippage assumptions. Shadow results remain separate. Never relabel a no-entry as a win or omit it from coverage reporting.

---

# V7-13. SIGNAL, DELIVERY, LIFECYCLE, AND PERFORMANCE TRUTH

Define immutable candidate identity and per-user delivery identity separately.

A canonical event ledger records every lifecycle transition with prior state, new state, version, quote/provider evidence, event time, processing time, actor, reason and idempotency key.

State transitions use optimistic versioning/CAS or appropriate row locks. Illegal, duplicate, out-of-order and regressive transitions are rejected and audited.

Delivery truth requires Telegram API success plus persisted chat ID, message ID, sent timestamp, payload/template version and `sent_ok=true`. An uncertain Telegram result enters reconciliation. Queued/reserved/stored is not delivered.

Performance truth:

- only proof-backed delivered signals in live advisory statistics;
- user-specific visibility and delivery proof;
- show denominator, tracked count, outcome coverage and confidence interval where meaningful;
- separate strategy, asset class, market type, timeframe, profile, tier, provider and regime;
- preserve losses, SL, missed entry, expiry, cancellation, provider failure and unavailable outcome;
- separate paper, shadow, backtest, walk-forward, demo execution and real execution;
- include fees/spread/slippage/latency assumptions where relevant;
- no public win-rate claim before minimum coverage/sample gate and statistical review.

The same-user same-asset repeat lock defaults to four hours, direction agnostic, and starts only after proof-backed delivery. It must reconstruct after Redis loss.

---

# V7-14. USERS, ENTITLEMENTS, PROFILES, PRIVACY, AND EXPERIENCE

Implement canonical roles/tiers `free`, `premium`, `vip`, `admin`, `owner` and profiles `scalp`, `day`, `swing`, `position`, `all` unless an explicit later decision changes them.

Entitlements must be calculated by one versioned policy using subscription state, role, promotional/referral grants, expiry, manual admin grants and feature release phase. Persist provenance. Never scatter tier checks throughout handlers.

User settings include terms version/time, privacy version/time, timezone, travel mode, language, quiet hours, notifications, assets, timeframes, minimum score, risk preferences, paper settings, execution consent and broker account selection.

Every command and callback must scope data to the authenticated Telegram user and authorised role. Add IDOR and cross-user tests.

User-facing errors must explain whether a feature is unavailable, disabled by policy, missing data, market closed, provider degraded, subscription required, or temporarily retrying. Do not show technical secrets or misleading generic success.

---

# V7-15. PAYMENTS AND FINANCIAL LEDGER INTEGRITY

Use a double-entry or equivalently auditable immutable financial ledger for payment/entitlement/refund events where appropriate. Do not derive financial truth solely from mutable subscription rows.

Paystack requirements:

- initialise only from the server;
- use integer subunits and verified currency/plan amount;
- unique internal and provider references;
- HMAC verification over the exact raw webhook body;
- fast acknowledgement and async durable processing;
- server-side transaction verification;
- match reference, amount, currency, customer, plan and environment;
- idempotent webhook and verification convergence;
- entitlement and receipt committed atomically with an outbox event;
- immutable receipt number and content hash;
- test/live key and data separation;
- duplicate, replay, wrong amount, failed, reversed, refunded, dispute and timeout tests;
- reconciliation against provider records;
- real payouts remain disabled until separately certified.

Never activate public prices or paid tiers while exact pricing/business policy is unresolved.

---

# V7-16. BROKER EXECUTION, METAAPI, COPY TRADING, AND SMART DCA

Every order path calls one canonical execution application service. Telegram handlers, strategies, paper engines and DCA logic cannot call broker SDKs directly.

Execution intent state machine:

```text
CREATED → VALIDATING → RESERVED → SUBMITTING → ACKNOWLEDGED
→ OPEN/PARTIALLY_FILLED/FILLED → MODIFYING/CLOSING → CLOSED
```

Failure/uncertainty states include `REJECTED`, `CANCELLED`, `EXPIRED`, `UNKNOWN_RESULT`, `RECONCILING`, and `FAILED_TERMINAL`.

Before broker I/O validate consent, tier, mode, account ownership, demo/live classification, quote freshness, symbol spec, trade permission, balance/equity/free margin, market hours, spread, slippage budget, geometry, total portfolio risk, daily loss/drawdown, kill switch, lot step/minimum/maximum and idempotency reservation.

Use Decimal calculations and round size down. No fake equity, fallback balance, fixed 0.01 lot, unverified symbol mapping, or minimum-lot promotion that exceeds risk.

Persist request hash, client idempotency key, broker request/result, broker order/position IDs, timestamps, account ID, symbol spec snapshot, quote, risk calculation and reconciliation result. Unknown result must be reconciled before retry.

MetaApi certification uses a dedicated demo account and proves deployment/synchronisation, quote/spec/account state, order/modify/close/history, reconnect, rejection, timeout and idempotency. Native Windows MT5 is not claimed to run inside Railway Linux.

Smart DCA is off by default; per-user/per-signal, monotonic DCA1 then DCA2, no averaging after stop/invalidation, total risk bounded, original signal proof required, canonical execution router only.

Copy trading requires independent leader/follower consent, allocation rules, symbol mapping, equity/risk scaling, slippage, partial failure, disconnect, reconciliation, kill switches, legal review and pilot evidence.

---

# V7-17. ML, GEMINI, MODEL RISK, AND DATA LINEAGE

The live Railway monolith collects telemetry and performs bounded inference only. Heavy training, hyperparameter search, SHAP, broad replay and batch feature generation run offline or in a separate controlled service.

Create data lineage from source market data through features, candidate, decision, delivery, outcome and training row. Dataset manifests include schema version, row count, time range, instruments, provider provenance, code commit, feature versions, exclusions, label policy and cryptographic hash.

Prevent leakage. Use chronological train/validation/test and walk-forward validation. Keep rejected/shadow candidates but never present counterfactual shadow results as delivered performance.

Model registry records model ID/version, algorithm, features, training dataset hash, metrics, calibration, limitations, owner, approval, deployment phase, shadow results, drift thresholds, rollback and expiry/review date.

Gemini:

- optional advisory component;
- structured output constrained by currently supported schema subset;
- Pydantic/domain semantic validation after schema validation;
- bounded timeout, retries, circuit and cost/rate budget;
- prompt/model/version/hash recorded;
- never sole source of direction, price, position size or execution approval;
- outage/malformed/429 response does not stop deterministic core;
- injection-resistant handling of news/user/provider content;
- no secrets or private broker credentials in prompts;
- evaluate hallucination, consistency and disagreement with deterministic gates.

---

# V7-18. SECURITY, PRIVACY, AND SUPPLY-CHAIN ASSURANCE

Map requirements and tests to the current stable OWASP ASVS, OWASP API Security Top 10, and the current final NIST SSDF; track newer draft standards separately rather than calling drafts final.

Perform threat modelling using assets, actors, trust boundaries, data flows, abuse cases and STRIDE-style categories. Include Telegram impersonation, webhook spoofing/replay, IDOR, privilege escalation, callback forgery, Redis poisoning, provider SSRF, prompt injection, secret leakage, payment replay, broker credential theft, order duplication, dependency compromise and insider/admin misuse.

Required controls:

- least privilege and deny by default;
- RBAC/ABAC and object-level authorisation;
- encrypted secrets and broker credentials;
- key rotation and credential revocation;
- hashed API/session tokens;
- constant-time secret comparisons;
- input size/schema validation;
- SSRF-safe outbound allowlists and DNS/IP validation where applicable;
- rate limits and resource quotas;
- secure headers/CORS/CSRF policy;
- log and artefact redaction;
- audit integrity and admin action confirmation;
- dependency pinning and vulnerability scanning;
- secret scanning;
- SBOM generation such as CycloneDX/SPDX;
- container image scanning and non-root runtime where compatible;
- reproducible build and provenance records;
- vulnerability disclosure/security contact documentation;
- backup encryption and access control;
- data retention/deletion/export workflows;
- privacy impact register and Nigeria/other applicable legal review marked as owner/legal decisions rather than invented compliance.

Security findings have severity, exploitability, affected releases, remediation, regression test and disclosure policy. Critical/high unresolved findings block public release.

---

# V7-19. OBSERVABILITY, TRACING, SLOS, AND ALERTING

Instrument with structured JSON logs, metrics and distributed traces. Prefer OpenTelemetry-compatible traces/metrics and propagate correlation/trace IDs through HTTP, Redis messages, DB operations, Telegram sends, provider calls, payments and broker calls.

Do not put high-cardinality user/signal IDs into metric labels; use exemplars/log correlation.

## V7-19.1 Required SLIs

- process/event-loop availability;
- webhook acceptance success and latency;
- command initial acknowledgement and completion latency;
- callback ACK latency;
- Telegram send success/RetryAfter/error;
- Redis stream append/read/ack/lag/pending/dead-letter age;
- DB session acquisition/hold/transaction latency and timeout;
- provider availability/freshness/latency/error/quota;
- signal cycle duration and queue age;
- candidate-to-delivery and proof-persistence latency;
- lifecycle/outcome lag and coverage;
- payment verification/reconciliation lag;
- execution reservation/submission/reconciliation lag;
- memory, CPU, task count and event-loop lag;
- feature-flag and deployment identity.

## V7-19.2 Initial owner-beta objectives

Treat these as initial engineering targets to validate and refine with measured baselines:

- webhook durable acceptance p95 ≤ 250 ms and p99 ≤ 1 s while RedisDelivery is healthy;
- callback ACK p95 ≤ 500 ms;
- command first response/ack p95 ≤ 1.5 s for local/DB-only commands;
- no critical DB session held over 10 s;
- zero unexplained webhook 503 responses;
- zero duplicate proven deliveries for the same reservation;
- Telegram pending updates return to zero under normal load;
- outcome tracker completes scheduled iterations without DB-admission timeout;
- delivery/lifecycle queue age remains within declared per-tier limits;
- readiness reflects real dependencies rather than process-only liveness.

Any changed target requires an ADR, measurement and owner-visible impact.

## V7-19.3 Alerting

Define severity and routing for migrations, readiness, webhook failures, pending updates, DB leaks, Redis lag, provider blackout, stale data, delivery failures, outcome lag, payment mismatch, execution unknown result, memory pressure and repeated task crash. Alerts must deduplicate, include runbook and correlation data, and avoid leaking secrets.

---

# V7-20. RELIABILITY, DISASTER RECOVERY, AND BUSINESS CONTINUITY

Define RPO/RTO by data class rather than using one vague target.

At minimum:

- PostgreSQL signal/payment/execution/audit truth: documented backup schedule, point-in-time capability where available, restore procedure and restore drill;
- RedisState: rebuildable, RPO may be zero durable reliance;
- RedisDelivery: persistence/backup policy plus PostgreSQL outbox reconciliation;
- source/config/secrets: versioned and recoverable without exposing secrets;
- provider/Telegram outage: degraded mode and catch-up policy;
- broker unknown result: reconciliation-first recovery;
- payment outage: pending/reconciliation state without double fulfilment.

Test:

- application restart with active signals;
- deploy rollback;
- DB failover/restart;
- PgBouncer restart;
- RedisState loss;
- RedisDelivery consumer death and restart;
- Telegram retries;
- provider outage and recovery;
- corrupted/poison message;
- partial migration failure;
- clock skew;
- dependency outage;
- restore from backup in isolated staging.

Maintain incident severity levels, commander, communications, containment, rollback, data-integrity check, postmortem and regression-test requirements.

---

# V7-21. PERFORMANCE, CAPACITY, LOAD SHEDDING, AND COST

Create explicit budgets for CPU, memory, DB connections, Redis connections, provider calls, Gemini calls, Telegram sends, queue depth and Railway spend.

Use bounded concurrency, semaphores, batching, deduped in-flight requests, caches with provenance/freshness, circuit breakers, backoff with jitter and load shedding.

Priority under pressure:

1. webhook durable acceptance;
2. callback/command acknowledgement;
3. delivery proof and reconciliation;
4. active lifecycle/outcomes;
5. payment/execution reconciliation;
6. new signal generation;
7. maintenance;
8. analytics/training/backfill.

Low-priority work must yield before critical work starves.

Load tests cover command bursts, callback bursts, 100,000-user eligibility/fan-out planning, provider throttling, Telegram RetryAfter, Redis lag, DB contention and active-outcome batches. Measure p50/p95/p99, throughput, memory, connection count and queue age. A planner-only simulation must not be reported as network delivery proof.

Create a cost report by feature and provider. Add spend/rate safeguards for Gemini and paid providers. Never silently exceed the owner’s configured budget.

---

# V7-22. CI/CD, REPRODUCIBLE BUILDS, AND RELEASE ENGINEERING

Required pipeline stages:

1. source formatting/lint;
2. type checking;
3. import/architecture checks;
4. unit/property/domain tests;
5. migration graph and clean PostgreSQL migration;
6. representative legacy migration;
7. Redis integration tests;
8. Telegram contract tests;
9. provider contract fixtures;
10. security/secret/dependency scans;
11. SBOM generation;
12. container build and scan;
13. integration/E2E suite;
14. coverage and mutation thresholds;
15. artefact signing/checksums/provenance;
16. staging deployment and safe live probes;
17. manual approval for activation phases.

Pin direct and transitive dependencies with hashes where tooling supports it. Record Python, OS, package and container versions. Do not auto-update dependencies directly in production without the full pipeline.

Every release has semantic version, Git tag, migration range, config-schema version, feature-flag changes, compatibility notes, rollback steps, evidence bundle and known blockers.

Database migration rollback must be forward-fix when destructive downgrade is unsafe. Application rollback compatibility with migrated schema must be tested.

---

# V7-23. AUTOMATIC FULL DEPLOYMENT DIAGNOSTICS

Build one orchestrator that can run in modes:

- `predeploy-core`;
- `runtime-safe`;
- `staging-live`;
- `full-certification`;
- `destructive-chaos` with explicit approval.

Every check outputs:

- stable check ID;
- description;
- phase;
- start/end/duration;
- result: `PASS`, `FAIL`, `WARN`, `BLOCKED_EXTERNAL`, `DISABLED_BY_POLICY`, `NOT_APPLICABLE`, `SKIPPED_REQUIRES_APPROVAL`;
- evidence/reference;
- redacted details;
- remediation;
- whether it blocks readiness/release.

Pre-deploy core verifies source identity, dependency integrity, environment schema, dangerous flags, migration graph/head, database migration readiness, PgBouncer configuration, Redis separation, command/route/callback registry, security scans and no placeholder enabled path.

Runtime safe verifies `/livez`, `/healthz`, `/readyz`, bot identity/webhook, queue state, command registration, active DB holders, task ownership, provider health and safe command probes.

Full certification may run live provider, Paystack test, TradingView, MetaApi demo, complete tests, load and mutation in an isolated service. It must not consume customer updates or place live orders.

Reports are stored outside ephemeral pre-deploy filesystem when retention is required; Railway pre-deploy filesystem changes are not assumed to persist.

---

# V7-24. TEST DATA, FIXTURES, PROPERTY TESTS, AND MUTATION TESTING

Use deterministic factories and anonymised fixtures. Never copy live secrets or unnecessary personal data into tests.

Build golden fixtures for:

- each asset class/market type/timeframe;
- bullish/bearish/ranging/volatile/illiquid/closed regimes;
- provider malformed/stale/delayed data;
- command/tier/profile combinations;
- signal lifecycle boundaries;
- Paystack events;
- TradingView alerts;
- MetaApi demo states;
- migration legacy schemas;
- Redis pending/dead consumer states.

Property tests include:

- signal geometry by direction;
- monotonic lifecycle and TP progression;
- idempotency under duplicate/reordered events;
- risk never exceeds configured maximum after rounding;
- same-user isolation;
- repeat lock begins only after proven delivery;
- no stored-only signal in delivered performance;
- money/subunit round trips;
- callback codec length/version/ownership;
- migration reconciliation preserves row/evidence counts;
- queue replay does not duplicate business effects.

Mutation score thresholds are higher for risk, lifecycle, delivery proof, payments, execution, auth and migrations. Surviving mutants require tests or an explicit documented exclusion.

Coverage excludes generated/vendor files only. Critical module branch coverage and mutation score are separately enforced; repository-wide percentages cannot hide untested critical code.

---

# V7-25. RAILWAY-SPECIFIC DEPLOYMENT CONTRACT

Create separate persistent `staging` and `production` environments with independent Postgres, RedisState, RedisDelivery, Telegram bots, domains, secrets and data.

Application service:

- one replica and one Uvicorn worker initially;
- no serverless sleep for background processing;
- bind Railway `PORT`;
- graceful shutdown/draining;
- exact commit/deployment/environment logged;
- healthcheck endpoint selected according to safe activation design;
- external continuous monitoring because Railway deployment healthchecks are not continuous;
- pre-deploy Alembic migration with no reliance on persistent filesystem or mounted volume;
- private service-to-service addresses;
- DB backup before risky migration and periodic restore drill;
- sealed secrets re-added per environment.

Use reference variables for internal database/Redis URLs. Use a direct Postgres URL for migrations when available and PgBouncer for runtime transaction pooling. Do not expose database or Redis publicly merely for convenience.

Initial production state:

```env
RUN_ENGINE_LOOP=0
RUN_WORKER_LOOP=1
WS_INGEST_ENABLED=0
CRYPTO_WS_ENABLED=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
FREE_SIGNAL_DISTRIBUTION_ENABLED=0
TELEGRAM_ALLOW_PAID_BROADCAST=0
PAYMENTS_PUBLIC_ENABLED=0
REAL_PAYOUTS_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
MT5_ALLOW_LIVE_ACCOUNTS=0
```

Activation remains phased. Never activate all features simultaneously.

---

# V7-26. EXACT RELEASE GATE MATRIX

## Gate A — code integrity

- no syntax/import errors;
- locked dependencies install from clean environment;
- type/lint/architecture/security scans meet thresholds;
- no enabled placeholder/stub;
- requirements traceability has no unknown P0/P1 item.

## Gate B — database and infrastructure

- one Alembic head;
- clean and legacy migrations pass on real PostgreSQL;
- deployed DB at head;
- PgBouncer contract tests pass;
- no unlabelled/nested/long-held sessions;
- RedisState and RedisDelivery distinct and healthy;
- task ownership unique.

## Gate C — Telegram command recovery

- webhook 2xx acceptance and pending count zero;
- no unexplained 503;
- command registry equals runtime registration;
- every safe command probe passes;
- every visible callback/button ACKs and completes;
- engine-off/degraded-mode commands work;
- no cross-user access.

## Gate D — owner-only crypto advisory

- engine enabled only for crypto REST;
- providers certified;
- no WebSocket task;
- one exact signal completes delivery/lifecycle/outcome proof;
- stored-only signals excluded from metrics;
- four-hour repeat lock proven.

## Gate E — owner soak

- 24–72 hours stable;
- no DB admission timeout/session leak;
- no duplicate/stale delivery;
- no unexplained webhook error;
- queues, memory, CPU and connections stable;
- restart/Redis recovery pass.

## Gate F — asset expansion

Enable FX, commodities, equities, indices and derivatives one at a time. Each requires provider, calendar, instrument mapping, strategy/risk and lifecycle certification.

## Gate G — limited users and subscriptions

Internal testers, limited free, Premium/VIP beta; command/button matrix and support runbook complete.

## Gate H — payments

Paystack test-mode E2E, replay/wrong amount/refund/reconciliation/receipt, legal/business prices approved. Only then controlled paid beta.

## Gate I — execution

Paper → MetaApi demo → controlled demo users → separately approved real-execution pilot. Real execution requires additional legal/risk/security review and kill-switch demonstration.

---

# V7-27. OPERATIONS, ADMINISTRATION, SUPPORT, AND GOVERNANCE

Provide owner/admin operational commands and protected HTTP/CLI tools for:

- health/readiness/diagnostics;
- provider and queue state;
- DB session holders;
- delivery reconciliation;
- active signals/outcomes;
- user/tier/subscription lookup;
- receipts/payments/reconciliation;
- broker/execution reconciliation;
- feature flags and kill switches;
- audit search;
- safe replay/quarantine;
- incident mode.

Privileged mutations require role, recent authentication or confirmation as appropriate, dry-run, impact preview, idempotency and immutable audit.

Support workflow includes ticket/reference ID, user consent before viewing sensitive data, response templates, payment/broker escalation, incident banner/status, data export/deletion request tracking and retention policy.

Create governance for thresholds, strategies, providers, models, prices, legal text, terms/privacy versions and execution permissions. Changes require version, approver, effective time, rollback and user notification where applicable.

---

# V7-28. DOCUMENTATION DELIVERABLES

Produce:

- architecture overview and ADRs;
- C4/context/container/component diagrams;
- sequence diagrams for every critical path;
- ERD and data dictionary;
- event/API/callback schemas;
- command and button catalogue;
- user/tier/profile product guide;
- provider capability matrix;
- strategy/indicator/risk specification;
- lifecycle/outcome semantics;
- PgBouncer and DB session guide;
- Redis stream/recovery guide;
- Railway deployment and rollback runbook;
- migrations/legacy reconciliation runbook;
- Telegram incident runbook;
- payment and execution runbooks;
- threat model and security verification mapping;
- observability/SLO/alert catalogue;
- disaster recovery/restore runbook;
- testing and evidence guide;
- operator/admin/support handbook;
- ML/model governance documentation;
- release notes and known blockers.

Documentation must match executable registries and be checked in CI for drift where possible.

---

# V7-29. CODING-AGENT WORKFLOW AND ANTI-ABANDONMENT PROTOCOL

Execute vertical slices in this order:

1. corpus/forensic inventory and requirement mapping;
2. repository skeleton, configuration, IDs, time, numeric types;
3. PostgreSQL/PgBouncer unit of work and migrations;
4. RedisState/RedisDelivery and outbox/inbox;
5. Telegram webhook, dispatcher, command/callback registry and certification harness;
6. users/terms/tiers/profiles/entitlements;
7. instrument master/provider registry/market data;
8. strategies/features/scoring/risk;
9. signal persistence, delivery proof and repeat protection;
10. lifecycle/outcomes/performance;
11. paper/shadow/replay/backtest/walk-forward/ML telemetry;
12. Gemini/news/macro/on-chain;
13. TradingView and Paystack;
14. MetaApi demo execution;
15. observability/security/DR/load/chaos;
16. Railway staging proof and soak;
17. phase-gated expansion.

For each slice:

- write requirements and acceptance tests first;
- reproduce relevant legacy incident;
- implement domain/application/infrastructure/interface;
- run unit/property/integration/migration tests;
- update traceability and docs;
- commit;
- generate evidence;
- only then continue.

Do not ask repeated questions. Consolidate missing credentials, business decisions, permissions and legal inputs into one blocker register. Continue every unblocked task.

Never claim that a path was “tested” when it was only mocked. Use exact labels: mocked unit, fixture contract, local integration, Railway staging, public endpoint, sandbox, demo, live.

---

# V7-30. REQUIRED FINAL ARTEFACTS AND RESPONSE

Return all of the following:

1. clean source repository ZIP;
2. Git patch from supplied baseline;
3. Git history/commit map;
4. checksums;
5. evidence ZIP;
6. requirement/decision/conflict/incident/blocker registries;
7. legacy line-disposition manifest;
8. architecture/ERD/sequence diagrams;
9. complete test reports;
10. coverage and mutation reports;
11. security/SBOM/container reports;
12. migration reports for clean and legacy DBs;
13. command/button certification matrix;
14. provider certification matrix;
15. same-signal lifecycle evidence;
16. Railway configuration and environment registry;
17. runtime diagnostics report;
18. soak/load/chaos evidence;
19. payment/TradingView/MetaApi evidence where available;
20. final completion report with exact evidence-backed verdict.

Final response sections:

- Executive verdict;
- Inputs and source reconstruction;
- Requirements coverage and conflicts;
- Architecture delivered;
- Data/migration/PgBouncer proof;
- Telegram command/button proof;
- Market/provider/signal/lifecycle proof;
- Payments/execution/ML status;
- Security/reliability/observability proof;
- Tests and exact results;
- Railway deployment and activation status;
- Downloadable artefacts and checksums;
- Remaining blockers and permissions;
- Next release gate.

---

# V7-31. ANTI-SHORTCUT AND ANTI-HALLUCINATION RULES

The implementation is invalid when any of these occur:

- renaming a broken function and calling it fixed;
- adding a test that asserts only importability or HTTP 200 while semantics remain untested;
- accepting 401/403/503 as successful feature proof;
- suppressing exceptions to make tests green;
- changing fail-closed gates to fail-open;
- lowering thresholds to generate activity;
- using old/stale/synthetic data as live;
- using queue insertion as delivery proof;
- using generated/stored rows as user performance;
- claiming every command works from registration count;
- increasing DB connections to hide session leaks;
- enabling WebSockets to hide REST/provider gaps;
- using `create_all()` to bypass migrations;
- stamping Alembic without schema verification;
- deleting duplicate/history rows to satisfy a unique index;
- using fake equity or fallback lot size;
- retrying uncertain broker orders without reconciliation;
- fulfilling payment from client callback alone;
- silently defaulting unresolved business/legal decisions;
- marking missing credentials as test success;
- reporting mocked or simulated results as live evidence;
- leaving an enabled feature without rollback and kill switch;
- declaring completion before required soak/live proof.

---

# V7-32. CURRENT PRIMARY-SOURCE IMPLEMENTATION BASELINE

At implementation time, re-check current official documentation. The 2026-07-27 baseline to verify includes:

- Railway pre-deploy runs after build and before deployment, fails the deployment on non-zero exit, runs in a separate container, and does not preserve filesystem changes or mount volumes.
- Railway deployment healthchecks gate activation but are not continuous monitoring.
- Railway private networking is isolated per environment and uses internal service DNS.
- PgBouncer transaction pooling reassigns server connections at transaction boundaries and does not support session-bound assumptions such as session advisory locks or `LISTEN`.
- Modern PgBouncer can support protocol-level prepared statements when configured, while SQLAlchemy/asyncpg prepared-statement caches still require explicit compatible configuration.
- Python asyncio cancellation requires `try/finally`; `CancelledError` is a `BaseException`; structured concurrency with `TaskGroup` should not have cancellation swallowed.
- Telegram retries non-2xx webhook delivery and supports the secret-token header.
- Redis Streams consumer groups provide at-least-once delivery through `XREADGROUP`/`XACK`; pending work can be reclaimed with `XAUTOCLAIM`.
- Paystack requires server authentication, amount in currency subunits, webhook-origin verification, idempotency and transaction verification.
- TradingView webhook receivers must respond within its documented timeout and must not embed credentials; TradingView warns that alerts are not themselves an automated-trading authority.
- Gemini structured outputs support only a subset of JSON Schema and still require semantic validation.
- MetaApi exposes REST and WebSocket APIs and must be proven with a demo account before any execution release.
- OWASP ASVS and API Security Top 10 provide security verification and API-abuse baselines.
- NIST SSDF final and draft versions must be labelled accurately.
- OpenTelemetry Python traces and metrics are stable; logs maturity/status must be checked before relying on it.

Primary reference URLs are included in the source-reference appendix of the prompt pack. Do not copy limits or behaviour from blogs when official documentation exists.

---

# V7-33. FINAL V7 INSTRUCTION

Build SignalRankAI completely from the supplied corpus under this V7 contract. Preserve every valid V6 and historical requirement, but do not preserve unsafe architecture. Produce working code and evidence rather than promises. Keep unproven or dangerous capabilities disabled. Resolve all locally solvable gaps. Surface only genuine external/business/legal/live-proof blockers. Do not stop until the repository, verification, documentation and release artefacts are complete to the strongest evidence-supported stage.

---

# APPENDIX A — COMPLETE V6 PROMPT PRESERVED VERBATIM

The text below is the complete input V6 prompt, preserved byte-for-byte after normal UTF-8 reading. V7 has precedence where conflicts exist; otherwise every V6 requirement remains binding.

# SIGNALRANKAI V6 — CLEAN-SLATE, PRODUCTION-GRADE, FULL-ECOSYSTEM MASTER BUILD PROMPT

**Purpose:** give this prompt to a capable coding agent together with the latest SignalRankAI source archive and all available project documents/logs. The agent must build SignalRankAI as a clean, coherent, production-grade system from scratch while preserving every valid product requirement, user-facing workflow, business rule, safety invariant, and hard-earned engineering lesson from the existing project.

**Prompt generation date:** 2026-07-27  
**Primary deployment target:** Railway, PostgreSQL behind PgBouncer transaction pooling, two Redis services, Telegram webhook mode, one coordinated application process and one Uvicorn worker for the initial owner-beta release.  
**Primary product identity:** Telegram-first, multi-user, multi-asset trading-intelligence ecosystem with deterministic market analysis, optional AI/ML review, proof-backed delivery, complete signal lifecycle tracking, paper/shadow/backtest/walk-forward separation, subscriptions/payments readiness, and independently gated broker execution.

---

# 0. ABSOLUTE OPERATING CONTRACT

You are the principal architect, staff backend engineer, quantitative systems engineer, database engineer, SRE, security engineer, test architect, Telegram product engineer, payments engineer, broker-integration engineer, and release manager for SignalRankAI.

You are not being asked for a plan, checklist, sketch, pseudo-code demonstration, partial prototype, tutorial, or speculative architecture. You are being asked to **produce the complete working repository**, tests, migrations, deployment configuration, diagnostics, documentation, evidence, and release package.

You must not:

- claim a feature works because a file, function, route, command, adapter, migration, or test name exists;
- claim production readiness from compilation or unit tests alone;
- preserve broken legacy behaviour merely for compatibility;
- silently remove a historical feature or command;
- invent credentials, prices, permissions, legal decisions, provider entitlements, live evidence, or broker capabilities;
- turn an unavailable dependency into a fake success;
- use synthetic data as live production evidence;
- mix generated, stored, reserved, delivered, paper, shadow, backtest, walk-forward, demo-executed, or real-executed results;
- lower quality gates merely to create activity;
- guarantee profit, a 60% win rate, or any minimum return;
- keep a database transaction/session open across Telegram, provider, Gemini, Paystack, MetaApi, Redis blocking waits, sleeps, or CPU-heavy work;
- use runtime `create_all()`, ad-hoc schema mutation, or multiple schema owners in Railway;
- use session-level PostgreSQL features that are incompatible with PgBouncer transaction pooling;
- enable public payments, real payouts, copy trading, Smart DCA, or real-money execution before their independent release gates pass;
- finish with “done”, “production-ready”, or equivalent unless every required evidence gate is satisfied.

No prompt can mathematically guarantee zero defects. Therefore, interpret “no mistakes and no gaps” as a binding requirement to create explicit invariants, automated tests, runtime diagnostics, fault injection, release gates, and honest blocked statuses so that defects are discovered rather than hidden.

---

# 1. SOURCE-OF-TRUTH AND PRECEDENCE

Use these sources in this exact order:

1. The latest explicit owner instruction.
2. This V6 clean-slate master prompt.
3. The Cross-Chat Decision Ledger and Universal Requirement Register appended below.
4. The latest source archive and its tests, migrations, documentation, runtime profiles, and proof manifest.
5. The latest Railway logs and incident evidence.
6. Earlier SignalRankAI master prompts and historical documents appended below.
7. Older code paths only as compatibility evidence, never as authority over newer decisions.

When sources conflict:

- record the conflict in a decision ledger;
- apply the latest explicit decision;
- preserve the older behaviour behind a disabled compatibility adapter only when data migration or user continuity requires it;
- never silently choose a value;
- keep public activation disabled if a business decision such as pricing is unresolved.

Treat the latest archive as a **behavioural specification and forensic evidence source**, not as an architecture that must be copied. Rebuild cleanly. Reuse proven algorithms or tests only after understanding them, correcting them, and placing them behind clear contracts.

---

# 2. MANDATORY FORENSIC RECONSTRUCTION BEFORE IMPLEMENTATION

Before writing the replacement system, perform a repository-wide forensic pass.

## 2.1 Every-file and every-line accountability

For every file in the supplied archive:

- calculate SHA-256, size, line count, language/type, category, imports, public symbols, environment-variable reads, database/table references, routes, Telegram handlers, callbacks, provider calls, broker calls, payment calls, and test references;
- parse every owned Python file with AST;
- identify dynamic imports, monkey patches, fallback imports, duplicated symbols, shadowed modules, unreachable branches, placeholders, stubs, broad exception swallowing, fake defaults, dangerous fallbacks, blocking calls in async code, and import-time side effects;
- classify every file and meaningful code region as `PRESERVE_BEHAVIOUR`, `REIMPLEMENT`, `MERGE`, `DEPRECATE`, `DELETE_GENERATED_ONLY`, `TEST_ONLY`, `DOCUMENTATION_ONLY`, or `UNKNOWN_REQUIRES_REVIEW`;
- create a Line Accountability Manifest mapping every production source file to requirements, new modules, tests, and disposition;
- do not delete a capability merely because it is poorly implemented;
- do not carry forward exploratory scripts, stale patch scripts, duplicate migration trees, cached artefacts, bytecode, or contradictory TODO documents into the clean production root.

## 2.2 Runtime-path reconstruction

Trace complete call graphs for:

- process startup and shutdown;
- Alembic pre-deploy;
- FastAPI lifespan;
- Telegram `setWebhook`, webhook ingress, queueing, dispatch, handler routing, command completion, callback acknowledgement, replies, and diagnostics;
- user onboarding, terms, tier/profile/preferences, timezone/travel mode;
- market-universe discovery;
- provider selection and OHLC/quote fetching;
- signal generation, strategy orchestration, scoring, filters, risk, deduplication, storage, fan-out, delivery proof, active-message management, lifecycle transitions, outcomes, MFE/MAE and notifications;
- paper trading, shadow tracking, replay, backtest, walk-forward and ML export;
- Paystack initialise/verify/webhook/entitlement/receipt/refund/reconciliation;
- TradingView webhook ingestion;
- MetaApi/MT5 account linking, quote/spec/account checks, sizing, order placement, modification, close, reconciliation and idempotency;
- scheduler ownership, worker ownership, restart recovery and Redis reconstruction.

For each path, produce a sequence diagram and a truth table describing success, retryable failure, terminal failure, degraded mode, and evidence written.

## 2.3 Historical incident reconstruction

Create regression specifications for every known incident, including at minimum:

- Telegram commands and inline buttons registered but not responding;
- webhook `503 Service Unavailable`, pending Telegram updates, and opaque rejection reasons;
- a DB session held while refreshing active keyboards and making Telegram calls, causing critical-lane starvation;
- anonymous/unlabelled DB holders;
- nested DB sessions and event-loop-specific engine proliferation;
- PgBouncer transaction-pooling incompatibilities;
- `There is no current event loop in thread 'ThreadPoolExecutor-0_0'` during the market circuit check;
- WebSocket restart loops and all-provider circuit openings while REST data remained healthy;
- accidental free-user signal distribution during owner-only testing;
- duplicate active `(asset, direction, timeframe)` rows preventing a unique index;
- pre-existing `payment_receipts` table blocking Alembic;
- migrations referencing columns before their canonical creation revision;
- `decision_log.created_at` schema drift;
- waitlist import failures;
- placeholder proxy URL requests;
- stale signal resend scans;
- generated/stored signals contaminating delivered performance or exposure;
- Redis-empty state causing mass expiry or loss;
- outcome coverage near zero despite thousands of deliveries;
- signals sent repeatedly for the same asset/user;
- signal delivery rows reserved but not proven sent;
- callback data too long, stale, replayed, cross-user, or routed to the wrong handler;
- Binance regional restrictions and provider fallbacks silently misclassifying assets;
- yfinance timestamp/staleness defects;
- MT5 fake equity, fixed `0.01` fallback volume, unsafe account selection, duplicate orders, and direct broker calls bypassing the canonical router;
- Smart DCA averaging after stop, non-monotonic DCA levels, or cross-user state leakage;
- token-rotation tests weakened to accept a 401 as success;
- local module names shadowing third-party `telegram` packages;
- timezone-naive UTC handling;
- duplicate scheduler/task ownership;
- N+1 fan-out and resource starvation.

No incident is closed until there is a targeted regression test and a live/staging evidence requirement where applicable.

---

# 3. CLEAN-SLATE ARCHITECTURE

Build a new repository with strict domain/application/infrastructure/interface boundaries. The initial deployment may be one Railway service, but internal runtime roles must be separable without rewriting business logic.

## 3.1 Required top-level structure

Use a structure equivalent to:

```text
signalrankai/
  pyproject.toml
  README.md
  .env.example
  Dockerfile
  railway.json
  alembic.ini
  src/signalrankai/
    config/
    domain/
      users/
      entitlements/
      markets/
      signals/
      delivery/
      lifecycle/
      outcomes/
      portfolio/
      payments/
      execution/
      ml/
      audit/
    application/
      commands/
      queries/
      services/
      policies/
      unit_of_work.py
    infrastructure/
      postgres/
      redis_state/
      redis_delivery/
      telegram/
      providers/
      paystack/
      tradingview/
      metaapi/
      gemini/
      observability/
    interfaces/
      http/
      telegram/
      cli/
    runtime/
      app.py
      task_supervisor.py
      ownership.py
      resource_governor.py
    diagnostics/
    security/
  migrations/
  tests/
    unit/
    contract/
    integration/
    property/
    mutation/
    load/
    chaos/
    e2e/
    fixtures/
  scripts/
  docs/
  artefacts/
```

Equivalent naming is acceptable, but boundaries are not optional.

## 3.2 Dependency direction

- `domain` imports no framework, database, Redis, Telegram, provider, Paystack, MetaApi, Gemini, or Railway code.
- `application` imports domain contracts and abstract ports.
- `infrastructure` implements ports.
- `interfaces` translate HTTP/Telegram/CLI inputs into application commands and queries.
- runtime composition wires dependencies.
- tests can substitute every external port.
- no domain decision is hidden inside a Telegram handler, SQL query, provider adapter, or formatter.

## 3.3 One canonical operation per concern

There must be exactly one canonical implementation for:

- tier resolution;
- profile resolution;
- score resolution;
- asset classification;
- timeframe normalisation;
- quote/candle validation;
- signal geometry validation;
- delivery eligibility;
- repeat/cooldown policy;
- delivery proof;
- lifecycle transition rules;
- outcome projection;
- position sizing;
- broker execution routing;
- payment verification;
- command registration;
- callback encoding/routing;
- UTC time.

Compatibility aliases delegate to the canonical implementation and are covered by tests.

---

# 4. RUNTIME TOPOLOGY AND TASK OWNERSHIP

## 4.1 Initial Railway topology

Create four services in one isolated environment:

1. `SignalRankAI` application service.
2. `Postgres`.
3. `RedisState`.
4. `RedisDelivery`.

Initial application constraints:

- one replica;
- one process;
- one Uvicorn worker;
- webhook mode only;
- no polling;
- no serverless sleep;
- no hidden child process;
- no second scheduler;
- no duplicate outcome tracker;
- no duplicate engine loop;
- no runtime migration owner.

## 4.2 Runtime role registry

Create a declarative ownership registry for:

- Telegram webhook consumer;
- command/callback execution;
- signal engine;
- market monitor;
- outcome tracker;
- lifecycle notification sender;
- delivery reconciler;
- resend worker;
- free distribution worker;
- subscription expiry;
- waitlist monitor/capacity;
- payment reconciliation;
- provider health probes;
- resource governor;
- ML telemetry export;
- paper/shadow trackers;
- active-message refresh;
- cleanup/archive jobs.

At startup, validate that every singleton task has exactly one owner. Refuse readiness when duplicate ownership is detected.

## 4.3 Structured task supervision

Every background task must have:

- name and owner;
- startup delay;
- heartbeat;
- bounded iteration timeout;
- cancellation-safe cleanup;
- exponential backoff with jitter;
- failure counter and circuit state;
- last-success timestamp;
- restart policy;
- readiness/criticality classification;
- metrics and diagnostics;
- no unobserved task exceptions.

---

# 5. POSTGRESQL, PGBOUNCER, TRANSACTIONS, AND MIGRATIONS

PostgreSQL is the durable source of truth. The production connection is through PgBouncer transaction pooling unless explicitly proven otherwise.

## 5.1 PgBouncer transaction-pooling contract

Implement and test these rules:

- detect PgBouncer endpoints and support explicit `DB_PGBOUNCER_MODE=1`;
- use one shared SQLAlchemy async engine per process;
- use `NullPool` behind PgBouncer; do not stack a persistent SQLAlchemy queue pool on the external pooler;
- use `asyncpg` with statement cache disabled or explicitly configured for PgBouncer;
- use unique prepared-statement names when prepared statements are enabled;
- never rely on session-level `SET`, session advisory locks, `LISTEN`, preserved temporary tables, or any other session-bound state in transaction mode;
- use transaction-scoped locks only where required and release them within the same short transaction;
- set application name, connect timeout, command timeout, and statement/lock/idle transaction timeouts;
- use a direct migration URL when available; otherwise ensure every migration is PgBouncer-compatible;
- do not run DDL in the live application process;
- do not use runtime `create_all()`;
- do not share an `AsyncSession` across tasks;
- do not create one engine per event loop or scheduler invocation.

## 5.2 Unit-of-work and session ownership

The application/service layer owns transaction boundaries. Repository methods accept a session/unit-of-work rather than opening nested sessions.

Every session must have:

- non-empty operation label;
- priority class: `INTERACTIVE`, `CRITICAL`, `BACKGROUND`, or `ANALYTICS`;
- acquisition timeout;
- caller/task/thread/loop identity;
- cancellation-safe rollback/close/release in `finally`;
- long-held-session watchdog;
- metrics for opened, closed, active, waiting, timed out and errored sessions.

Enforce these invariants:

1. No nested session acquisition inside an active unit-of-work unless explicitly marked re-entrant and reusing the same session.
2. No DB session remains open during any external network call.
3. No session remains open while sleeping or waiting on a queue.
4. Query results are copied into immutable/plain snapshots before leaving the transaction.
5. Interactive Telegram commands have reserved capacity and bounded degradation.
6. Outcome tracking cannot be starved by maintenance, analytics, or active-keyboard refresh.
7. Long-held critical sessions over 10 seconds fail deployment diagnostics; over 30 seconds trigger a critical incident.

## 5.3 Outcome-tracker DB pattern

Use this exact architecture:

1. Short critical transaction reads a bounded page of active proof-backed signal IDs and immutable tracking data.
2. Close the transaction.
3. Batch fresh quotes once per unique asset outside the DB.
4. Compute candidate transitions outside the DB.
5. For each transition batch, open a short transaction, lock rows or use version/CAS, verify monotonic state, persist lifecycle event and outcome projection.
6. Commit and close.
7. Send Telegram notifications outside the DB.
8. Persist notification proof/idempotency in a separate short transaction.

## 5.4 Fresh schema and legacy upgrade path

Support two fully tested paths:

- clean database from zero to head;
- legacy database containing drift, duplicate rows, manually created tables, partially applied migrations, and existing evidence.

All migration logic must:

- inspect existing schema;
- reconcile legacy data deterministically before adding unique constraints;
- preserve signal, delivery, outcome, payment and audit history;
- never delete evidence merely to make a migration pass;
- write reconciliation audit records;
- be transactional where PostgreSQL allows;
- be idempotent against known legacy drift;
- have upgrade and downgrade policy documented;
- have tests using real PostgreSQL, not SQLite alone.

Required legacy cases include:

- duplicate active signal theses: retain one canonical active row and mark extras `superseded` with audit evidence;
- pre-existing `payment_receipts`: add/repair columns, constraints and indexes without deleting historical receipts;
- duplicate receipt identifiers or provider references: preserve rows with deterministic archival identifiers and audit status;
- missing `decision_log.created_at`;
- delivery-proof columns created in the correct migration order;
- partially stamped Alembic revisions;
- one and only one migration head.

Alembic pre-deploy is the only Railway schema owner.

---

# 6. REDIS STATE AND DELIVERY DESIGN

Use two logically and physically separate Redis services.

## 6.1 RedisState

Use for reconstructible acceleration only:

- provider health/circuits;
- market cache;
- runtime counters;
- user/tier/profile cache;
- kill switch cache;
- active-signal/outcome snapshots;
- dedup/repeat acceleration;
- locks whose durable truth is in PostgreSQL;
- rate limits;
- resource-governor state.

Loss of RedisState must not delete or terminally mutate durable signals. Rebuild from PostgreSQL.

## 6.2 RedisDelivery

Use Redis Streams for:

- Telegram update inbox;
- delivery jobs;
- notification jobs;
- payment/trading webhook work where appropriate;
- dead-letter and reconciliation queues.

Implement:

- `XADD` with bounded retention;
- consumer groups and named consumers;
- `XREADGROUP`;
- process-before-`XACK`;
- `XPENDING` diagnostics;
- `XAUTOCLAIM`/`XCLAIM` for dead-consumer recovery;
- bounded retries with jitter;
- per-message idempotency key;
- dead-letter stream;
- age/lag/pending/consumer metrics;
- replay and restart tests.

PostgreSQL remains the final evidence source. Redis delivery is at-least-once transport; application idempotency creates exactly-once intent.

## 6.3 Telegram ingress fallback

After validating the Telegram secret and payload:

- first attempt durable Redis stream append;
- optionally use a bounded local queue only as short-lived availability fallback when policy permits;
- never claim durable acceptance when only volatile memory accepted the update;
- return a fast 2xx only when the update has been safely accepted under the configured durability policy;
- return structured 503 with a reason code only when acceptance truly failed;
- expose queue backend, depth, lag, pending, dead letters and rejection reason in diagnostics.

---

# 7. CANONICAL DOMAIN MODEL AND TRUTH STATES

## 7.1 User and entitlement

Canonical roles/tiers:

- `free`
- `premium`
- `vip`
- `admin`
- `owner`

Canonical trader profiles:

- `scalp`
- `day`
- `swing`
- `position`
- `all`

Persist terms version/time, privacy preferences, timezone, travel mode, language, notifications, risk preferences, filters, paper settings, execution mode, broker consent and entitlement provenance.

## 7.2 Signal evidence separation

Use distinct records/fields for:

- candidate generated;
- rejected candidate;
- decision/gate result;
- stored signal;
- user eligibility;
- delivery reservation;
- Telegram send attempt;
- confirmed delivery proof;
- active-message projection;
- lifecycle state;
- outcome;
- paper action;
- shadow evaluation;
- backtest result;
- walk-forward result;
- demo execution;
- real execution.

No metric or UI may silently blend these categories.

## 7.3 Canonical signal lifecycle

Define one versioned state machine, for example:

```text
CANDIDATE
REJECTED
ELIGIBLE
STORED
RESERVED_FOR_DELIVERY
DELIVERY_FAILED
DELIVERED
WATCHING_FOR_ENTRY
ENTRY_TOUCHED
ACTIVE
TP1_HIT
TP2_HIT
TP3_HIT
STOPPED
MISSED_ENTRY
EXPIRED
CANCELLED
SUPERSEDED
```

Specify allowed transitions, terminal states, monotonic TP progression, version/CAS rules, event idempotency, timestamp semantics and notification rules.

Early-exit or opportunity-change warnings are advisory events and must not rewrite the official TP/SL/expiry outcome.

## 7.4 Delivery proof

A signal is delivered to a user only after:

- Telegram API returns success;
- durable delivery row has `sent_ok=true`;
- Telegram chat ID is persisted;
- Telegram message ID is persisted;
- sent timestamp and payload/version are persisted;
- idempotency/reservation state is finalised.

A generated, stored, reserved or queued row is not a delivery.

## 7.5 Repeat protection

Canonical same-user same-asset lock:

- four hours by default;
- direction agnostic;
- begins only after proven delivery;
- persists/reconstructs across restarts and Redis loss;
- coexists with active-position, exact-fingerprint, cross-timeframe thesis and stale-delivery gates;
- explicit owner-configured overrides must be centralised and tested.

Historical timeframe cooldown defaults to reconcile:

- 15m: 10 minutes;
- 1h: 20 minutes;
- 4h: 90 minutes;
- 1d: 6 hours.

---

# 8. MULTI-ASSET MARKET-DATA PLATFORM

## 8.1 Required market coverage

Architect for genuine support of:

- crypto spot;
- crypto perpetuals;
- crypto dated futures;
- crypto options;
- forex;
- commodities spot/CFD/futures where provider support is explicit;
- equities;
- equity/index ETFs;
- indices;
- equity options;
- futures;
- volatility/yield/macro instruments;
- broker-specific instruments and synthetics only when the linked demo/live broker exposes and classifies them.

Never relabel a derivative as spot or an index proxy as the underlying index without provenance.

## 8.2 Canonical market types

Create strong typed identifiers containing:

- canonical asset ID;
- provider symbol;
- venue/exchange;
- asset class;
- market type;
- quote/base currency;
- expiry;
- strike;
- option type;
- contract multiplier;
- inverse/linear flag;
- timezone/session/calendar;
- price/quantity precision;
- minimum quantity/notional;
- real-time/delayed/historical provenance.

## 8.3 Canonical quote/candle contract

Every quote/candle must include:

- canonical asset and provider symbol;
- timeframe/interval;
- provider;
- exchange/venue;
- provider timestamp and receive timestamp;
- open/high/low/close/volume;
- bid/ask/mid/last where available;
- source latency;
- freshness age;
- delayed/realtime status;
- completeness and validation result;
- market-open/session status;
- data-quality warnings.

Reject NaN, impossible OHLC geometry, non-monotonic timestamps, duplicates, insufficient candles, stale data, wrong market type and unsupported timeframe.

## 8.4 Provider capability registry

Every provider has declarative metadata:

- supported asset classes and market types;
- timeframes;
- public/keyed/sandbox/live requirements;
- rate limits/quota policy;
- real-time versus delayed capabilities;
- regional restrictions;
- sample instruments;
- health state;
- certification status;
- fallback role;
- execution-truth eligibility.

Implemented/historical provider families to reconcile include:

- Coinbase;
- OKX;
- Kraken;
- KuCoin;
- Bybit;
- Binance, disabled by default where regionally unreliable;
- CryptoCompare;
- Deribit;
- CoinGecko legacy/fallback;
- Twelve Data;
- Polygon;
- Financial Modeling Prep;
- Alpha Vantage;
- OANDA;
- Tiingo;
- EODHD;
- Marketstack;
- Finnhub;
- Alpaca;
- Tradier;
- Stooq;
- Nasdaq Data Link;
- ECB;
- FCS;
- yfinance/Yahoo only as best-effort historical/delayed fallback, never sole execution truth.

An importable adapter is not certified. Maintain statuses such as `IMPLEMENTED_NOT_LIVE_VERIFIED`, `PUBLIC_ENDPOINT_VERIFIED`, `SANDBOX_VERIFIED`, `LIVE_VERIFIED`, `BLOCKED_MISSING_CREDENTIAL`, `BLOCKED_REGION`, `BLOCKED_PAID_PLAN`, `ANALYSIS_ONLY`, `UNSUITABLE_FOR_PRODUCTION`, `DISABLED`, and `FAILED`.

## 8.5 REST and WebSocket policy

REST is the correctness path for initial deployment.

WebSockets are optional optimisations and must:

- be disabled by default;
- have one canonical enable flag plus provider-specific flags;
- never start when disabled;
- supervise staleness, reconnects, backoff and circuits;
- reconcile tick-to-bar output against REST;
- not make the entire engine unavailable when every socket fails;
- be enabled one provider at a time after REST proof and soak.

## 8.6 Market hours and calendars

Use asset-specific exchange calendars, holidays, daylight-saving rules and session state. Distinguish market closed, provider unavailable, stale, and no valid signal. Notify users appropriately without producing false opportunities.

---

# 9. SIGNAL ENGINE, STRATEGIES, SCORING, AND RISK

## 9.1 Pipeline

Implement a deterministic, observable pipeline:

```text
universe discovery
→ capability and market-open checks
→ required timeframe fetch
→ data validation
→ feature/indicator calculation
→ regime and market-structure analysis
→ strategy orchestration
→ geometry validation
→ multi-timeframe consensus
→ technical/news/macro/on-chain context
→ scoring and calibration
→ expectancy gate
→ portfolio/exposure gate
→ dedup/repeat/cooldown gate
→ optional Gemini review
→ persist decision and signal
→ user/tier/profile eligibility
→ fresh final quote validation
→ delivery reservation
→ Telegram proof
→ lifecycle tracking
```

Every rejection/suppression has a durable reason code, metrics and ML telemetry.

## 9.2 Strategy families

Support and correctly classify at least:

- trend following;
- mean reversion;
- breakout;
- momentum;
- scalping;
- market structure;
- support/resistance break-and-retest;
- liquidity sweeps;
- order blocks;
- ICT concepts;
- Smart Money Concepts;
- VWAP;
- volume profile;
- Wyckoff;
- Fibonacci confluence;
- EMA/ADX/Supertrend;
- RSI/MACD/Stoch RSI;
- ATR/Bollinger/Keltner volatility;
- grid analysis for suitable non-directional contexts, never hidden martingale execution;
- pairs trading;
- statistical arbitrage;
- options flow and volatility context;
- macro/news-driven filters;
- on-chain context;
- commodity-specific strategy logic;
- deterministic emergency fallback strategies only when they still meet full geometry/risk/evidence gates.

Each strategy declares supported asset classes, market types, timeframes, required features, minimum data, expected holding range, invalidation logic and test fixtures.

## 9.3 Indicators and mathematical correctness

Implement and property-test all indicators and maths used, including ATR, ADX, EMA, RSI, MACD, stochastic RSI, Bollinger Bands, Keltner Channels, VWAP, volume profile, pivots, support/resistance, Fibonacci, order blocks, liquidity, volatility, trend/regime, correlation, beta, expectancy, reward/risk, slippage, spread, position sizing, MFE and MAE.

No placeholder constant such as a fixed average reward/risk may be used in production decisions.

## 9.4 Scoring

Create one explainable score schema with components, weights, penalties and calibration. Do not allow arbitrary aliases to silently override each other. Store raw components and final resolved score. Detect score saturation at 0 or 100. Use calibration and reliability diagrams rather than trusting nominal confidence.

Quality is preferred over frequency. The historic 60% win-rate goal is a research objective only.

## 9.5 Risk

Required advisory and execution risk controls:

- valid direction and entry/SL/TP geometry;
- positive reward/risk and expectancy threshold;
- quote freshness and drift limits;
- spread/slippage/liquidity checks;
- asset/sector/correlation exposure;
- per-user active trade and daily loss/drawdown limits;
- tier/profile risk policy;
- market regime and news conflict;
- stop distance/volatility sanity;
- portfolio concentration;
- fail closed when critical state is missing;
- no fake balances or minimum-lot promotion that increases risk.

---

# 10. TELEGRAM PRODUCT ARCHITECTURE

Telegram is the primary interface for the current release.

## 10.1 Declarative command registry

Build one command registry containing:

- command name and aliases;
- description/help page;
- required terms version;
- role/tier entitlement;
- feature flags;
- rate limit;
- DB priority;
- execution timeout;
- mutation classification;
- audit policy;
- required fixtures;
- handler;
- response schemas/snapshots;
- safe live-probe classification.

Generate handler registration, `/help`, BotFather command lists, access checks, diagnostics and tests from this registry. Duplicate registrations are a build failure unless explicitly mutually exclusive and tested.

## 10.2 Webhook ingress

- validate `X-Telegram-Bot-Api-Secret-Token` with constant-time comparison;
- reject malformed updates safely;
- record/update idempotency by Telegram `update_id`;
- enqueue durably and return quickly;
- never block on a DB query or command execution in the HTTP request;
- preserve pending updates during normal redeploys;
- expose `getWebhookInfo`, pending count and last error;
- every non-2xx path logs a structured reason and reference ID.

## 10.3 Command execution middleware

Every command must:

- record received/started/completed/failed/timed-out lifecycle;
- respond or acknowledge quickly;
- use bounded execution timeout;
- use interactive DB priority;
- close DB before Telegram send;
- provide a friendly degraded response with reference ID;
- redact secrets;
- enforce tier/role/ownership;
- be idempotent for mutations;
- be testable with a dedicated staging user/chat.

## 10.4 Callback architecture

Use one versioned compact callback codec/router. Every callback must:

- ACK immediately before heavy work;
- validate version/action/payload length;
- validate requesting user owns or may access the target;
- reject stale/replayed actions safely;
- be idempotent;
- route to exactly one handler;
- have DB and snapshot fallback behaviour;
- have expiry and backward compatibility policy;
- never expose raw sensitive IDs when an opaque token is safer.

Required visible actions include:

- Check Outcome;
- Open Signal;
- Monitor;
- Taking It;
- Watching;
- manual/paper Take Trade;
- profile selection;
- pricing/upgrade;
- receipt/support;
- paper controls;
- broker controls;
- pagination;
- confirmation/cancellation;
- terms acceptance/decline;
- timezone/travel mode;
- waitlist join.

## 10.5 Active-message refresh

Never hold a DB session while calling Telegram.

Required pattern:

1. Read a bounded snapshot of active messages, signal data, outcomes and engagements in one background transaction.
2. Close session.
3. Update Telegram messages with bounded concurrency and timeout.
4. Persist update proof/errors in short transactions.

Disable startup bulk refresh by default on Railway; schedule delayed bounded one-shot only after webhook readiness.

---

# 11. USER EXPERIENCE, TIERS, PROFILES, AND COMMAND SURFACE

Implement every command in the repository-derived command inventory appended to this prompt. For each command, either:

- implement a complete production workflow;
- map it to a documented alias;
- deliberately retire it with an owner-approved migration and user-facing replacement.

A placeholder response is not implementation.

At minimum preserve the canonical product behaviour described in the historical V5 specification appended below, including free, Premium, VIP, admin and owner catalogues; profile workflows; paper trading; diagnostics; referrals; support; receipts; broker status; Automaton/Codex/Gemini controls; and all owner-beta probes.

Public prices must come from one versioned business-policy configuration. If exact prices are unresolved, keep public payment activation off and surface `BLOCKED_BUSINESS_DECISION`.

---

# 12. DELIVERY, FAN-OUT, AND USER ISOLATION

## 12.1 Eligibility

Eligibility must consider user status, terms, tier, profile, asset/timeframe preferences, quiet hours/timezone, daily quota, score threshold, existing deliveries, active positions, repeat lock, subscription state and feature flags.

## 12.2 Batch fan-out

Design for at least 100,000 users without N+1 queries:

- fetch audience and entitlements in batches;
- compute policy in vectorised/batched form;
- reserve delivery rows with unique constraints/idempotency;
- enqueue bounded jobs;
- honour Telegram rate limits and `RetryAfter`;
- do not let one invalid chat block others;
- persist per-user proof/error;
- reconcile uncertain sends.

## 12.3 User isolation

Prove there is no cross-user data leakage in commands, callbacks, `/signals`, portfolios, preferences, broker accounts, receipts, referrals, execution or diagnostics. Add IDOR tests and tenant/user-scoped repository contracts.

---

# 13. LIFECYCLE, OUTCOMES, PERFORMANCE, AND EARLY EXIT

Track complete lifecycle with fresh trusted quotes and asset-specific rules.

Persist:

- entry touch time/price;
- active time;
- each TP hit time/price;
- SL time/price;
- missed/expired reason;
- MFE/MAE absolute, percentage and R;
- duration;
- spread/slippage assumptions;
- provider/provenance;
- notification proof;
- lifecycle version and event ledger.

Performance queries must use proof-backed delivered signals only and show coverage/sample size. Separate asset class, tier, profile, strategy and timeframe. Never hide losses, missed entries, expiry, provider outages or unavailable outcomes.

Early-exit intelligence may warn about regime/structure/news/opportunity changes but must not rewrite the original outcome.

---

# 14. PAPER, SHADOW, BACKTEST, REPLAY, AND WALK-FORWARD

Implement separate engines/data domains for:

- user paper trading;
- system paper execution;
- shadow tracking of rejected candidates;
- deterministic replay;
- backtesting;
- walk-forward optimisation;
- orderbook/tick simulation where data exists.

Include realistic fees, spreads, slippage, latency, partial fills, missed entries, contract multipliers and market hours. Prevent look-ahead, survivorship and leakage. Persist configuration and dataset version. Never merge these statistics with live delivered outcomes.

---

# 15. ML TELEMETRY, OFFLINE LEARNING, AND GEMINI

## 15.1 Telemetry-first design

Capture both issued and rejected candidates with:

- identity/provenance;
- all raw/derived market features;
- regime, structure, liquidity, volatility, spread and session;
- strategy outputs;
- gate decisions and reasons;
- score components;
- user/tier/profile eligibility;
- provider latency/failures;
- delivery latency/proof;
- lifecycle/outcome/MFE/MAE/duration;
- shadow counterfactual results.

## 15.2 Training boundary

Do not perform heavy continuous training, SHAP, broad replay or hyperparameter search on the live Railway monolith. Provide export, offline training, validation, model card, calibration, drift, approval, rollback and shadow deployment.

Prevent leakage and synthetic-data contamination. Promotion requires reproducible dataset hash, feature schema, code version, time split/walk-forward results and independent live shadow evidence.

## 15.3 Gemini

Gemini is optional advisory intelligence, never the sole deterministic gate. Use structured JSON-schema output, semantic validation, model/version provenance, bounded timeout, retry/circuit, rate/spend budget and safe fallback. Malformed or semantically impossible responses must not pass. Gemini outage must not stop deterministic analysis.

---

# 16. NEWS, MACRO, ON-CHAIN, AND MARKET INTELLIGENCE

Build source reliability, deduplication, timestamps, entity/asset mapping, sentiment, event severity, fake-news/rumour risk, embargo/calendar awareness and provenance. Use news/macro/on-chain as context/gates, not unverified truth. Persist the exact evidence used for each signal.

---

# 17. TRADINGVIEW

Implement a dedicated authenticated ingestion path with:

- HTTPS;
- strict payload schema;
- HMAC/shared-secret or certificate/IP validation strategy;
- timestamp/freshness window;
- event ID idempotency;
- replay protection;
- symbol/asset mapping;
- geometry validation;
- normal signal/risk/delivery gates;
- quick acknowledgement because TradingView cancels slow webhooks;
- no credentials in URL/body;
- complete audit and staging test.

TradingView alerts are inputs, not automatic authority to trade.

---

# 18. PAYSTACK, SUBSCRIPTIONS, RECEIPTS, REFUNDS, AND REFERRALS

Implement:

- server-side transaction initialisation;
- callback handling as UX only, not final truth;
- server-side verification;
- webhook HMAC-SHA512 over raw body;
- fast 200 acknowledgement and asynchronous processing;
- event idempotency;
- amount/currency/plan/user matching;
- entitlement transaction;
- receipt generation and immutable receipt ledger;
- duplicate/replay handling;
- failed/reversed/refunded states;
- support/refund request workflow;
- reconciliation job;
- test/live environment separation;
- no double fulfilment;
- audit events and admin lookup.

Public payments and real payouts remain off until Paystack test-mode E2E and reconciliation pass.

---

# 19. PAPER, METAAPI/MT5, COPY TRADING, AUTO-EXECUTION, AND SMART DCA

## 19.1 Release separation

Advisory signals are one release. Paper trading is another. MetaApi demo execution is another. Real execution/copy trading is an independently approved release.

## 19.2 Canonical execution router

Every execution path—manual-confirmed, semi-auto, auto, copy, tiered execution and Smart DCA—must call one canonical router. No Telegram handler or strategy may call a broker client directly.

## 19.3 Execution gates

Require:

- explicit accepted terms and per-action/per-mode consent;
- approved tier and execution mode;
- encrypted credential custody;
- account ownership and demo/live classification;
- fresh broker quote;
- broker symbol specification;
- balance/equity/free margin;
- valid entry/SL/TP geometry;
- risk-based size rounded down to broker step;
- minimum volume/notional validation without unsafe promotion;
- kill switch and daily drawdown guard;
- one idempotency/reservation record before broker I/O;
- broker acknowledgement persisted;
- order/position reconciliation;
- timeout/unknown-result recovery;
- immutable execution ledger;
- no fixed `0.01` fallback and no fake equity.

## 19.4 Smart DCA

Default off. Per-user/per-signal state. Monotonic DCA1 then DCA2. No averaging after stop invalidation. Position risk remains bounded across all legs. Uses the canonical router and original proof-backed signal.

## 19.5 MetaApi

Use demo accounts for certification. Test account deployment/status, quote, symbol spec, account data, order, modify, close, history, reconciliation, disconnect/reconnect, rejection and idempotency. Native Windows MT5 must not be pretended to run inside Railway Linux.

---

# 20. HTTP/API, ADMIN, WEB DASHBOARD, AND SECURITY

Provide versioned APIs for health/readiness, diagnostics, user-safe signals, token rotation/revocation, provider/broker status, Paystack, TradingView and admin functions.

Security requirements:

- authentication and RBAC;
- tenant/user scoping;
- anti-IDOR;
- rate limiting;
- replay/idempotency;
- secret redaction;
- encrypted credentials;
- key rotation;
- token hashes, never plaintext persistence;
- CSRF/CORS as appropriate;
- secure headers;
- input/schema validation;
- dependency and container scanning;
- audit logs;
- privacy/data-retention controls;
- no secret in Telegram callback data, logs, URLs or generated artefacts.

Privileged commands/actions require explicit confirmation and immutable audit.

---

# 21. OBSERVABILITY, DIAGNOSTICS, AND INCIDENT RESPONSE

## 21.1 Health model

Implement:

- `/livez`: process/event-loop liveness;
- `/healthz`: cheap health summary;
- `/readyz`: strict dependency/runtime readiness;
- protected `/diagnostics/deployment`;
- protected `/diagnostics/commands`;
- metrics endpoint.

Use `/readyz` for deployment activation when appropriate. Railway healthchecks are deployment-time activation checks, not continuous monitoring; configure external continuous monitoring and alerts.

## 21.2 Metrics

At minimum:

- event-loop lag;
- process memory/CPU/tasks;
- DB admission/pool/session hold duration;
- Redis latency, stream depth, group lag, pending and dead letters;
- Telegram webhook pending/errors, queue age, handler latency, callback ACK latency, send latency/RetryAfter/failures;
- provider latency/error/staleness/circuit/quota;
- candidate/gate/rejection/storage/reservation/delivery counts;
- proof-persistence latency;
- lifecycle/outcome lag and coverage;
- payment event/reconciliation;
- execution reservation/order/reconciliation;
- scheduler/task health;
- Gemini usage/rate/budget.

## 21.3 Automatic deployment diagnosis

Pre-deploy must run secret-safe checks and fail on core blockers. Runtime diagnosis must verify the live process and classify every check as `PASS`, `FAIL`, `WARN`, `BLOCKED_EXTERNAL`, `DISABLED_BY_POLICY`, or `NOT_APPLICABLE`.

Include:

- exact Git/deployment identity;
- environment contract and dangerous flags;
- one migration head/current revision/schema constraints;
- PgBouncer mode and engine/session configuration;
- both Redis services and separation;
- Telegram identity/webhook/queue/handler registry;
- safe command probe in dedicated staging chat;
- provider certification;
- signal/delivery/lifecycle evidence;
- Paystack/TradingView/MetaApi checks when credentials exist;
- active DB holders and long sessions;
- task ownership;
- package/dependency consistency;
- route/command/callback duplicate audit;
- static/security/coverage/mutation results;
- missing details reported as blocked rather than passed.

---

# 22. COMPLETE TEST AND VERIFICATION PROGRAMME

## 22.1 Test layers

Create:

- unit tests;
- domain invariant tests;
- property-based tests;
- contract tests for every external adapter;
- real PostgreSQL integration tests;
- PgBouncer transaction-pooling tests;
- Redis Stream integration/recovery tests;
- Telegram handler/callback snapshot and E2E tests;
- provider public/sandbox/keyed certification;
- Paystack test-mode E2E;
- TradingView signed webhook E2E;
- MetaApi demo E2E;
- migration clean/legacy/partial/drift tests;
- load, soak and chaos tests;
- security tests;
- mutation tests;
- static typing/lint/dependency/container scans.

## 22.2 Every command and button

Inventory the full command/callback graph automatically. Classify commands into:

- safe automatic live probes;
- fixture-dependent semantic tests;
- explicit-permission/money/credential/system mutations.

Do not blindly auto-run dangerous commands. Build deterministic fixtures and owner-approved test procedures so every command and visible button is eventually proven end to end.

## 22.3 Coverage

Set enforced coverage thresholds with stricter requirements for critical modules. Coverage alone is not proof; combine branch coverage, mutation score, property invariants and E2E evidence. No threshold may be waived silently.

## 22.4 Required full lifecycle proof

Prove one exact signal ID through:

```text
candidate
→ decision/gates
→ stored signal
→ user eligibility
→ delivery reservation
→ Telegram success
→ sent_ok/chat/message proof
→ active message
→ watching for entry
→ entry touched or missed
→ active
→ TP/SL/expiry
→ MFE/MAE/duration/R
→ outcome projection
→ user notification proof
→ performance query
```

Also prove stored-but-undelivered signals never contaminate exposure or performance.

## 22.5 Failure matrix

Test provider timeout/429/401/403/5xx/malformed/stale/empty/wrong symbol; Redis loss/reconnect; dead consumer; DB timeout; PgBouncer restart; Telegram 429/403/5xx/uncertain send; duplicate webhooks; app restart; partial migration; Gemini malformed/429/timeout; Paystack replay/wrong amount; MetaApi rejection/disconnect/unknown result; task crash; memory pressure; clock/timezone/DST boundaries.

---

# 23. RAILWAY BUILD, DEPLOYMENT, AND ACTIVATION

## 23.1 Deployment configuration

- private Git repository;
- Docker/Railpack build with pinned dependencies and reproducible lock;
- `bash start.sh` or equivalent single entrypoint;
- bind to Railway `PORT` and dual-stack-safe host where needed;
- Alembic in Railway pre-deploy;
- pre-deploy must not depend on persistent filesystem changes;
- strict readiness before traffic;
- one replica/one Uvicorn worker initially;
- deployment identity logged;
- rollback procedure and DB backup;
- separate persistent staging and production environments with independent secrets/data/bots.

## 23.2 Environment phases

1. Commands + worker/outcome recovery, engine off.
2. Owner-only crypto REST.
3. Proof-backed lifecycle.
4. 24–72-hour soak.
5. Expand universe.
6. FX.
7. Commodities.
8. Equities.
9. Indices.
10. Derivatives.
11. WebSockets one provider at a time.
12. Internal testers.
13. Limited free users.
14. Premium/VIP beta.
15. Paystack test then controlled paid beta.
16. Paper and MetaApi demo.
17. Separately approved real-execution pilot.

Never activate everything simultaneously.

## 23.3 Release gates

Before engine activation:

- migrations/head/schema pass;
- no anonymous or long-held DB session;
- outcome tracker runs without timeout for at least one hour;
- webhook returns 2xx and pending count reaches zero;
- safe command probe passes;
- REST market data works;
- WebSocket worker remains disabled;
- both Redis services healthy;
- no duplicate task ownership.

Before public release:

- same-signal lifecycle proof;
- 24–72-hour soak;
- no duplicate/stale delivery;
- stable resource usage;
- acceptable outcome coverage;
- all enabled asset providers certified;
- command/button matrix complete;
- security and payment gates complete.

---

# 24. OFFICIAL DOCUMENTATION RESEARCH REQUIREMENT

At implementation time, browse and verify the current official documentation for every external dependency. Use primary sources only.

The current research baseline includes:

- Railway pre-deploy commands run between build and deployment in a separate container; failures block deployment; filesystem changes are not persisted.
- Railway healthchecks gate deployment activation but are not continuous monitoring.
- Railway private networking is environment-isolated.
- PgBouncer transaction pooling does not support session-level state such as session advisory locks; the application must cooperate.
- SQLAlchemy documents PgBouncer/asyncpg use with `NullPool`, unique prepared-statement names, and careful prepared-statement configuration.
- Telegram retries unsuccessful non-2xx webhooks and supports `secret_token` through `X-Telegram-Bot-Api-Secret-Token`.
- Redis Streams consumer groups require `XREADGROUP`/`XACK` and support pending-message recovery with `XAUTOCLAIM`.
- Paystack webhooks require quick `200 OK`, HMAC-SHA512 verification and idempotent server-side value delivery; transaction verification remains necessary.
- TradingView webhook requests have tight processing limits and must not contain credentials.
- Gemini structured outputs still require semantic validation and rate/spend controls.
- MetaApi provides REST and WebSocket APIs and must be certified with a demo account.

Do not freeze implementation to this summary; re-check official docs because APIs, limits and platform behaviour can change.

---

# 25. REQUIRED DELIVERABLES

Deliver a repository containing:

1. Complete production source.
2. Clean migration chain and legacy import/reconciliation tooling.
3. Full automated test suite.
4. Static/type/security/dependency/container configurations.
5. Provider capability registry and live certification script.
6. Declarative Telegram command and callback registry.
7. Safe live command probe.
8. Automatic deployment diagnostics.
9. Runtime health/readiness/metrics.
10. Railway staging and production profiles.
11. Environment-variable registry with type/default/required/secret/phase/owner/deprecation metadata.
12. Data model/ERD.
13. Architecture and sequence diagrams.
14. Threat model.
15. Incident and rollback runbooks.
16. Product/tier/profile/command documentation.
17. ML feature schema, export format, model card template and governance.
18. Paystack, TradingView and MetaApi integration runbooks.
19. Clean source ZIP, patch, checksums and evidence bundle.
20. A completion report that distinguishes local proof, staging proof, live proof, blocked external items and disabled-by-policy items.

---

# 26. DEFINITION OF DONE

The project is not done until:

- every valid historical requirement is mapped to implementation and evidence;
- every production file/line in the supplied archive has a documented disposition;
- no placeholder, dead button, unimplemented command, fake provider, unsafe fallback, silent exception or contradictory configuration remains in an enabled path;
- all migrations pass from clean and representative legacy databases;
- PgBouncer tests pass;
- every command and callback is registered, authorised, ACKed, completed and semantically tested;
- one exact signal completes the full proof-backed lifecycle;
- all enabled providers are genuinely certified;
- outcome coverage and sample sizes are honest;
- no generated/stored-only evidence contaminates live metrics;
- staging restart, Redis recovery and fault tests pass;
- 24–72-hour soak passes;
- public payments and execution remain disabled until their separate gates pass;
- the final verdict uses only evidence-supported language.

Allowed verdicts include:

- `WORK_IN_PROGRESS`
- `CODE_COMPLETE_BUT_LOCAL_GAPS_REMAIN`
- `CODE_COMPLETE_BUT_LIVE_PROOF_PENDING`
- `OWNER_BETA_READY`
- `PUBLIC_ADVISORY_RELEASE_READY`
- `DEMO_EXECUTION_PILOT_READY`
- `REAL_EXECUTION_PILOT_READY`

Never skip directly to the strongest verdict.

---

# 27. EXECUTION WORKFLOW FOR THE CODING AGENT

Proceed without stopping at a plan:

1. Materialise and hash all inputs.
2. Build the forensic manifest and requirement/decision ledgers.
3. Reproduce current failures with tests.
4. Design the clean domain and ports.
5. Create the new repository and migration head.
6. Implement vertical slices, beginning with configuration/time/DB/Redis/Telegram ingress.
7. Implement user/tier/profile and command registry.
8. Implement provider platform and market-data contracts.
9. Implement signal engine, decisions, risk, storage and proof delivery.
10. Implement lifecycle/outcomes.
11. Implement paper/shadow/replay/backtest/ML telemetry.
12. Implement payments/TradingView.
13. Implement broker abstraction and demo-only execution.
14. Port or replace every historical command/callback/feature.
15. Run static, unit, property, integration, migration and load suites continuously.
16. Run clean-room Railway simulation.
17. Package source and evidence.
18. Produce exact staging instructions and blocked-input request.
19. After access is granted, perform staging proof and soak.
20. Update verdict honestly.

When blocked by an external secret or permission, continue all other work and produce a single consolidated blocker register. Never fabricate the blocked result.

---

# 28. FINAL RESPONSE FORMAT FOR THE CODING AGENT

Return:

## A. Executive verdict
Exact allowed verdict and why.

## B. Source reconstruction
Files, lines, requirements, decisions, conflicts and dispositions.

## C. Architecture delivered
Runtime, domain, data, queues, providers, Telegram, payments, execution and ML.

## D. Defects found and fixed
Root cause, code changes and regression proof.

## E. Verification
Commands run, pass/fail/blocked, coverage, mutation, security and live evidence.

## F. Railway deployment
Services, settings, migrations, environment profiles, health/readiness and activation order.

## G. Downloadable artefacts
Source ZIP, patch, evidence ZIP, checksums, reports.

## H. Remaining blockers
Only genuine external/business/legal/live-proof blockers.

---

# 29. REPOSITORY-DERIVED REFERENCE APPENDICES

The following inventories are extracted from the latest supplied codebase and are binding discovery inputs. They do not imply that every item is correct or should be copied unchanged.

## 29.1 Latest archive inventory summary

- Files inventoried: **887**
- Python files found by independent AST inventory: **657**
- Python source lines: **148645**
- `deployment_configuration`: **28**
- `documentation`: **77**
- `migration`: **24**
- `production_runtime`: **457**
- `project_asset`: **125**
- `script`: **35**
- `test`: **141**
- Environment-variable names referenced: **673**
- Unique Telegram commands found: **146**
- HTTP route decorators found: **27**
- Database/table names discovered: **55**
- Provider/connector files discovered: **45**

## 29.2 Critical legacy module map

| LOC | Path | Functions | Classes | Clean-slate disposition |
|---:|---|---:|---:|---|
| 8426 | `signalrank_telegram/bot.py` | 173 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 8242 | `signalrank_telegram/commands.py` | 171 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 4741 | `engine/core.py` | 114 | 13 | Forensic reference; split/reimplement behind clean contracts |
| 3679 | `db/pg_features.py` | 89 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 2649 | `data/fetcher.py` | 92 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 2554 | `railway_main.py` | 58 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 1826 | `engine/realtime_outcome_tracker.py` | 51 | 4 | Forensic reference; split/reimplement behind clean contracts |
| 1432 | `services/mt5_signal_router.py` | 31 | 4 | Forensic reference; split/reimplement behind clean contracts |
| 1409 | `signalrank_telegram/formatter.py` | 44 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1292 | `data/market_data.py` | 34 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 1243 | `engine/signal_deduplicator.py` | 54 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 1237 | `signalrank_telegram/owner_commands.py` | 23 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1207 | `db/session.py` | 50 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 1157 | `core/redis_state.py` | 71 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 1146 | `scripts/deployment_diagnostics.py` | 29 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 1075 | `ml/train_model.py` | 16 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1054 | `data/get_live_price.py` | 31 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 1038 | `data/providers.py` | 33 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1021 | `tests/test_enterprise_features.py` | 0 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1008 | `services/mt5_client.py` | 31 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 1008 | `core/resource_governor.py` | 32 | 11 | Forensic reference; split/reimplement behind clean contracts |
| 980 | `web/app.py` | 28 | 5 | Forensic reference; split/reimplement behind clean contracts |
| 928 | `signalrank_telegram/tier_signal_formatter.py` | 27 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 899 | `services/gemini_ml.py` | 25 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 897 | `engine/strategies/signal_generator.py` | 24 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 877 | `engine/risk.py` | 18 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 817 | `engine/delivery_freshness.py` | 23 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 739 | `db/models.py` | 1 | 42 | Forensic reference; split/reimplement behind clean contracts |
| 735 | `engine/admin_pulse.py` | 10 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 702 | `engine/ml_weighting.py` | 18 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 694 | `data/pair_discovery.py` | 24 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 691 | `core/trade_tracker.py` | 34 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 642 | `engine/signal_controller.py` | 29 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 616 | `core/paper_ledger.py` | 16 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 605 | `signalrank_telegram/command_access.py` | 8 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 592 | `engine/ml.py` | 23 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 591 | `scripts/asset_capability_audit.py` | 10 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 585 | `utils/command_registry.py` | 7 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 569 | `worker/worker.py` | 23 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 566 | `scripts/live_production_evidence.py` | 17 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 558 | `services/mt5_bridge.py` | 28 | 5 | Forensic reference; split/reimplement behind clean contracts |
| 549 | `engine/stale_signal_validator.py` | 19 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 545 | `data/ws_ingest.py` | 16 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 535 | `core/tier_policy.py` | 13 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 534 | `services/trading_mode_manager.py` | 17 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 514 | `signalrank_telegram/callback_handlers.py` | 14 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 513 | `engine/threshold_optimizer.py` | 14 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 512 | `engine/signal_lifecycle.py` | 11 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 508 | `engine/price_fetcher.py` | 20 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 505 | `services/subscription_manager.py` | 14 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 499 | `data/market_hours.py` | 12 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 491 | `db/repository.py` | 19 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 486 | `engine/wfo.py` | 11 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 485 | `db/auto_ops.py` | 5 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 484 | `engine/analytics.py` | 22 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 472 | `tests/test_deploy_log_regressions.py` | 46 | 15 | Forensic reference; split/reimplement behind clean contracts |
| 470 | `services/economic_calendar.py` | 12 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 469 | `engine/similarity.py` | 14 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 452 | `strategies/fallback.py` | 6 | 5 | Forensic reference; split/reimplement behind clean contracts |
| 452 | `engine/advanced_filters.py` | 18 | 9 | Forensic reference; split/reimplement behind clean contracts |
| 449 | `engine/scoring.py` | 20 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 447 | `db/mt5_models.py` | 11 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 446 | `engine/confluence_engine.py` | 18 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 444 | `engine/ranking.py` | 13 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 440 | `services/codex_governance.py` | 10 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 439 | `engine/tiered_executor.py` | 15 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 437 | `data/indicators.py` | 22 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 436 | `engine/tier_notifications.py` | 12 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 435 | `core/redis_streams.py` | 20 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 433 | `strategies/imp.py` | 20 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 430 | `engine/smart_dca.py` | 17 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 424 | `services/broadcaster.py` | 16 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 423 | `services/asset_mapper.py` | 5 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 419 | `signalrank_telegram/signal_commands.py` | 10 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 416 | `engine/backtest.py` | 24 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 411 | `engine/price_validator.py` | 9 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 406 | `tests/test_broker_execution_p0.py` | 15 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 399 | `signalrank_telegram/tier_delivery.py` | 18 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 399 | `engine/regime.py` | 14 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 397 | `strategies/tradingview.py` | 7 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 392 | `signalrank_telegram/admin_commands.py` | 9 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 389 | `engine/public_track_record.py` | 11 | 4 | Forensic reference; split/reimplement behind clean contracts |
| 384 | `engine/webhook_generator.py` | 10 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 378 | `data/provider_catalog.py` | 9 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 378 | `core/event_bus.py` | 20 | 3 | Forensic reference; split/reimplement behind clean contracts |
| 376 | `ml/signal_calibrator.py` | 12 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 375 | `scripts/run_complete_system_test.py` | 5 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 374 | `ml/dynamic_threshold.py` | 11 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 373 | `engine/correlation_engine.py` | 14 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 372 | `payments/invoice_service.py` | 14 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 371 | `tests/test_phase4_pass2_db_priority_and_command_speed.py` | 29 | 5 | Forensic reference; split/reimplement behind clean contracts |
| 369 | `tests/test_phase4_pass3_delivery_reliability.py` | 47 | 8 | Forensic reference; split/reimplement behind clean contracts |
| 365 | `scripts/reconcile_signal_lifecycle.py` | 7 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 363 | `engine/ultra_quality_filter.py` | 9 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 362 | `test_near_zero_loss.py` | 5 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 361 | `tests/test_phase4_pass1_quote_contract.py` | 22 | 0 | Forensic reference; split/reimplement behind clean contracts |
| 358 | `engine/strategy_orchestrator.py` | 11 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 353 | `services/dead_letter_queue.py` | 14 | 1 | Forensic reference; split/reimplement behind clean contracts |
| 353 | `engine/advanced_exit_manager.py` | 9 | 2 | Forensic reference; split/reimplement behind clean contracts |
| 352 | `tests/test_trade_tracker.py` | 18 | 1 | Forensic reference; split/reimplement behind clean contracts |

## 29.3 Telegram command inventory

The clean build must account for all of these command names and aliases:

- `/about`, `/account`, `/admin`, `/admin_broadcast`, `/admin_dashboard`, `/admin_feedback`, `/admin_payment_lookup`, `/admin_receipt_lookup`
- `/admin_signal_lookup`, `/admin_subscription_fix`, `/admin_top_assets`, `/admin_top_strategies`, `/admin_user`, `/admin_user_engagement`, `/alerts`, `/all_asset_test_status`
- `/analyze`, `/apikey`, `/asset_capability`, `/asset_class_test`, `/assets`, `/automaton_pause`, `/automaton_report`, `/automaton_reset_paper`
- `/automaton_resume`, `/automaton_status`, `/blast_terms`, `/broadcast`, `/cancel`, `/codex_audit`, `/codex_fix_plan`, `/codex_generate_issue`
- `/codex_log_review`, `/codex_pr_summary`, `/codex_refactor_plan`, `/codex_release_check`, `/codex_security_scan`, `/codex_test_plan`, `/contact_admin`, `/correct_signal`
- `/dashboard`, `/db_health`, `/delivery_debug`, `/delivery_eligibility`, `/dev_force_signal`, `/dev_invalidate`, `/dev_pause`, `/dev_resume`
- `/disclaimer`, `/drawdown`, `/early`, `/elite`, `/engine_debug`, `/execution`, `/faq`, `/feedback`
- `/filter`, `/force_market_scan`, `/force_signal`, `/format_debug`, `/gemini`, `/gemini_analyze`, `/gemini_audit`, `/gemini_predict`
- `/gemini_review`, `/help`, `/history`, `/invite`, `/language`, `/leaderboard`, `/liveprice`, `/market`
- `/mission`, `/mode`, `/mt5`, `/mt5_link`, `/mt5_status`, `/mt5link`, `/myid`, `/mystats`
- `/notify`, `/ohlc_health`, `/ops_health`, `/outcome`, `/owner_revenue`, `/owner_test_delivery`, `/owner_users`, `/paper_balance`
- `/paper_history`, `/paper_performance`, `/paper_positions`, `/paper_reset`, `/paper_settings`, `/payment_help`, `/performance`, `/performance_truth`
- `/policy`, `/portfolio`, `/pricing`, `/profile`, `/profile_debug`, `/proof`, `/provider_health`, `/provider_status`
- `/public_test_status`, `/qa_report`, `/quality`, `/recap`, `/receipt`, `/receipts`, `/referral`, `/referral_leaderboard`
- `/referral_rewards`, `/refund_request`, `/refunds`, `/release_guard`, `/report`, `/report_issue`, `/reports`, `/risk`
- `/selfcheck`, `/setlot`, `/setrisk`, `/settings`, `/setwebhook`, `/shadow_report`, `/signal`, `/signal_debug`
- `/signal_quality`, `/signals`, `/simulate`, `/start`, `/stats`, `/status`, `/strategy_leaderboard`, `/support`
- `/system`, `/tester_feedback`, `/tiers`, `/timezone`, `/travelmode`, `/unlock`, `/upgrade`, `/version`
- `/why_no_signal`, `/winrate`

## 29.4 Database/table inventory

- `account_ledger`, `active_signal_messages`, `active_signals`, `admin_events`, `alert_prefs`, `api_tokens`, `asset_live_metrics`, `bot_events`
- `dead_letter_queue`, `decision_log`, `economic_events`, `free_signal_queue`, `handles`, `managed_assets`, `market_candles`, `market_candles_ts`
- `market_ticks`, `ml_past_training_data`, `ml_rejected_signals`, `ml_shadow_predictions`, `ml_training_events`, `mt5_accounts`, `mt5_credentials`, `mt5_execution_log`
- `mt5_executions`, `mt5_positions`, `outcome_notifications`, `outcomes`, `outcomes_ts`, `paper_positions`, `payment_events`, `payment_receipts`
- `processed_webhook_events`, `provider_health`, `proxy_nodes`, `referral_codes`, `referral_rewards`, `referrals`, `runtime_state`, `signal_context`
- `signal_corrections`, `signal_deliveries`, `signal_engagements`, `signal_event_notifications`, `signal_lifecycles`, `signal_tracking_events`, `signals`, `strategy_live_metrics`
- `strategy_stats`, `subscriptions`, `trades`, `user_webhooks`, `users`, `vip_waitlist`, `virtual_accounts`

## 29.5 Provider adapter inventory

- `data/connectors/alpaca_adapter.py`
- `data/connectors/alphavantage_adapter.py`
- `data/connectors/binance_adapter.py`
- `data/connectors/bybit_adapter.py`
- `data/connectors/coinbase_adapter.py`
- `data/connectors/cryptocompare_adapter.py`
- `data/connectors/deribit_adapter.py`
- `data/connectors/ecb_adapter.py`
- `data/connectors/eodhd_adapter.py`
- `data/connectors/fcs_adapter.py`
- `data/connectors/finnhub_adapter.py`
- `data/connectors/fmp_adapter.py`
- `data/connectors/kraken_adapter.py`
- `data/connectors/kucoin_adapter.py`
- `data/connectors/marketstack_adapter.py`
- `data/connectors/nasdaq_data_link_adapter.py`
- `data/connectors/oanda_adapter.py`
- `data/connectors/okx_adapter.py`
- `data/connectors/polygon_adapter.py`
- `data/connectors/stooq_adapter.py`
- `data/connectors/tiingo_adapter.py`
- `data/connectors/tradier_adapter.py`
- `data/connectors/twelvedata_adapter.py`
- `data/connectors/yfinance_adapter.py`

## 29.6 Legacy environment-variable compatibility inventory

Create a typed canonical registry, map aliases, detect conflicts and mark obsolete variables deprecated. Do not copy defaults blindly. Legacy names observed:

- `ACTIVE_SIGNAL_COOLDOWN_IGNORE_EXPIRED_BY_TIME`, `ACTIVE_SIGNAL_LOOKBACK_HOURS`, `ADAPTIVE_LEARNING_BATCH_SIZE`, `ADMIN_ASSET_COOLDOWN_HOURS`, `ADMIN_ID`, `ADMIN_WEEKLY_REPORT_HOUR_UTC`, `ADMIN_WEEKLY_REPORT_WEEKDAY`, `AI_FEEDBACK_LAST_RUN`, `AI_JOURNAL_WEEKLY_DAY`, `AI_PROMPT_CONFIG_PATH`
- `AI_PROMPT_VERSION`, `ALLOW_PUBLIC_TESTING_IN_PRODUCTION`, `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPHAVANTAGE_API_KEY`, `ALPHAVANTAGE_ENABLED`, `ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS`, `ANALYTICS_ML_TRAIN_STARTUP_DELAY_SECONDS`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`
- `API_TOKEN_PEPPER`, `APP_BASE_URL`, `APP_ENV`, `ASK`, `ASSET_BLACKLIST`, `ASSET_CLASSES_ENABLED`, `ASSET_FETCH_DELAY_JITTER`, `ASSET_FETCH_DELAY_SECONDS`, `ASSET_LEARNING_ASSETS_PER_CYCLE`, `ASSET_LEARNING_CONCURRENCY`
- `ASSET_LEARNING_CRYPTO_LIMIT`, `ASSET_LEARNING_INTERVAL_SECONDS`, `ASSET_LEARNING_STOCK_LIMIT`, `ASSET_LEARNING_TIMEFRAMES`, `ASSET_REPEAT_LOCK_HOURS`, `ASSET_REPEAT_LOCK_REQUIRE_DELIVERED`, `ASSET_UNIVERSE_BACKGROUND_REFRESH_ENABLED`, `ATR`, `AUDIT_LOG_FILE`, `AUTOMATON_STARTING_BALANCE_USD`
- `AUTO_ANALYST_ENABLED`, `AUTO_ANALYST_INTERVAL`, `AUTO_DISCOVERY_ALL_PROVIDERS`, `AUTO_MAX_RISK_CAP_PCT`, `AUTO_MIGRATE`, `AUTO_OPTIMIZER_ENABLED`, `AUTO_OPTIMIZER_INTERVAL_SECONDS`, `AUTO_OPT_INTERVAL_HOURS`, `AUTO_OPT_MIN_TRADES`, `AUTO_OPT_TARGET_PERCENTILE`
- `AUTO_TRADE_ENABLED`, `BE_BUFFER_PCT`, `BID`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BOT_APP_DISCOVERY_TIMEOUT_SECONDS`, `BOT_COMMAND_AUDIT_TIMEOUT_SECONDS`, `BOT_INIT_STALE_SECONDS`, `BOT_MINIMAL_SCHEDULER_MODE`, `BOT_SCHEDULER_PERSISTENT_JOBSTORE_ENABLED`
- `BOT_START_ATTEMPT_TIMEOUT_SECONDS`, `BOT_USERNAME`, `BOT_WEBHOOK_READY_MIN_HANDLERS`, `BROADCASTER_MAX_PARALLEL`, `BROADCASTER_MAX_RETRIES`, `BROADCASTER_RETRY_DELAY`, `BROADCASTER_RETRY_MAX_DELAY`, `BROKER_EXEC_IDEMPOTENCY_SECONDS`, `BROKER_QUOTE_MAX_AGE_SECONDS`, `BROKER_RECONCILE_GRACE_MINUTES`
- `BROKER_RECONCILE_STALE_DAYS`, `BROKER_SANDBOX_ALLOW_ORDER`, `BTCUSDT`, `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYPASS_KEY`, `CACHE_DEFAULT_TTL_SECONDS`, `CANDLE_CACHE_PRUNE_SECONDS`, `CANDLE_FORWARD_FILL_TTL_SECONDS`, `CANDLE_REQUEST_CACHE_TTL_SECONDS`
- `CANDLE_STALENESS_MULTIPLIER`, `CHART_STYLE_DEFAULT`, `CHECK_OUTCOME_DB_TIMEOUT_SECONDS`, `CHECK_OUTCOME_SNAPSHOT_TIMEOUT_SECONDS`, `CIRCUIT_BREAKER_DROP_THRESHOLD_PCT`, `CIRCUIT_BREAKER_PRICE_PROVIDERS`, `CODEXOPS_MODE`, `CODEX_OPENAI_API_KEY`, `COINGECKO_API_KEY`, `COMMAND_HANDLER_TIMEOUT_SECONDS`
- `COMMODITY_PREFERRED_PROVIDER`, `COMMODITY_TICKERS`, `COMPLETE_SYSTEM_STEP_TIMEOUT_SECONDS`, `CONFLUENCE_GATE_MIN`, `CONFLUENCE_MIN_CEILING`, `CONFLUENCE_MIN_FLOOR`, `CONFLUENCE_MODERATE_RATIO`, `CONFLUENCE_STRONG_RATIO`, `CONFLUENCE_TOTAL`, `CONSENSUS_MIN_GROUPS`
- `CONSENSUS_REQUIRED_GROUPS`, `CORNIX_LEVERAGE`, `CORNIX_WEBHOOK_URL`, `CORRELATION_FILTER_MODE`, `CORRELATION_GUARD_ENABLED`, `CORRELATION_LOOKBACK_BARS`, `CRYPTOCOMPARE_API_KEY`, `CRYPTOPANIC_API_KEY`, `CRYPTO_BLACKLIST`, `CRYPTO_DATA_PROVIDER`
- `CRYPTO_DERIVATIVES_PROVIDERS`, `CRYPTO_MARKET_DATA_PROVIDERS`, `CRYPTO_MICROSTRUCTURE_PROVIDERS`, `CRYPTO_PAIRS`, `CRYPTO_PREFERRED_PROVIDER`, `CRYPTO_TIMEFRAMES`, `CRYPTO_TRENDING_TOP_N`, `CRYPTO_UNIVERSE_TOP_N`, `CRYPTO_WS_PROVIDER`, `CRYPTO_WS_SYMBOLS`
- `CYCLE_UNIVERSE_REFRESH_INTERVAL`, `DASHBOARD_URL`, `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_PASSWORD`, `DATABASE_PORT`, `DATABASE_SSLMODE`, `DATABASE_URL`, `DATABASE_USER`, `DB_APP_NAME`
- `DB_COMMAND_TIMEOUT`, `DB_CONNECT_BACKOFF_SECONDS`, `DB_CONNECT_MAX_ATTEMPTS`, `DB_CONNECT_TIMEOUT`, `DB_MAX_OVERFLOW_GLOBAL_CAP`, `DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP`, `DB_POOL_GLOBAL_CAP`, `DB_POOL_RAILWAY_ABSOLUTE_CAP`, `DB_ROLE`, `DB_SESSION_HOLD_WARN_SECONDS`
- `DB_SSLMODE`, `DB_START_TIMEOUT`, `DCA_PROFILE_DEFAULT`, `DECISION_LOG_WRITE_ENABLED`, `DEFAULT_ACCOUNT_BALANCE`, `DEFAULT_FIXED_LOT`, `DEFAULT_RISK_PCT`, `DEFAULT_RR`, `DEFAULT_TIMEFRAME`, `DEFAULT_TRADING_STYLE`
- `DEGRADED_MODE_MIN_CANDLES`, `DELIVERY_ASSET_LOCK_IGNORE_STALE_MINUTES`, `DELIVERY_DEDUPE_HOURS`, `DELIVERY_DEDUPE_RESET_EPOCH`, `DELIVERY_FRESHNESS_ERROR_FAIL_OPEN`, `DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN`, `DELIVERY_INFLIGHT_RETRY_SECONDS`, `DELIVERY_MARKET_COOLDOWN_MINUTES`, `DELIVERY_MISSING_PRICE_FAIL_OPEN`, `DELIVERY_RECEIPT_TTL_SECONDS`
- `DELIVERY_RECONCILE_BATCH_SIZE`, `DELIVERY_RECONCILE_INTERVAL_SECONDS`, `DELIVERY_REDIS_URL`, `DELIVERY_UNRESOLVED_BLOCK_HOURS`, `DEMO_ASSETS`, `DEMO_TIMEFRAMES`, `DEPLOYMENT_DIAGNOSTICS_KEY`, `DEPLOYMENT_DIAGNOSTICS_REPORT_PATH`, `DEPLOYMENT_DIAGNOSTICS_START_DELAY_SECONDS`, `DEPLOYMENT_DIAGNOSTICS_TIMEOUT_SECONDS`
- `DEPLOYMENT_DIAGNOSTIC_PROVIDERS`, `DEPLOYMENT_FULL_SUITE_TIMEOUT_SECONDS`, `DEPLOYMENT_MUTATION_TIMEOUT_SECONDS`, `DEPLOYMENT_QUEUE_MAX_GROUP_LAG`, `DEPLOYMENT_QUEUE_MAX_PENDING_AGE_SECONDS`, `DEPLOYMENT_SCANNER_TIMEOUT_SECONDS`, `DEPLOYMENT_SIGNAL_DISPATCH_MAX_DEPTH`, `DEV_MODE`, `DISABLED_ASSETS`, `DISCORD_WEBHOOK_DEFAULT`
- `DLQ_ALERT_THRESHOLD`, `DLQ_MAX_RETRIES`, `DLQ_RETRY_INTERVAL_HOURS`, `DRY_RUN`, `ECONOMIC_CALENDAR_CACHE_TTL_SECONDS`, `ECONOMIC_CALENDAR_TIMEOUT_SECONDS`, `ENABLE_CORRELATION_CHECK`, `ENABLE_ML`, `ENABLE_NEWS_SYNC`, `ENCRYPTION_KEY`
- `ENDGAME_FEATURES_ENABLED`, `ENGINE_ASSET_BLACKLIST`, `ENGINE_BASE_THRESHOLD`, `ENGINE_BRIEF_SECONDS`, `ENGINE_DIAGNOSTIC_DIR`, `ENGINE_MAX_CONCURRENCY`, `ENGINE_OUTCOME_TRACKER_ENABLED`, `ENGINE_PULSE_INITIAL_DELAY_SECONDS`, `ENGINE_PULSE_INTERVAL_SECONDS`, `ENGINE_TASK_RETRIES`
- `ENGINE_TASK_TIMEOUT_SECONDS`, `ENTRY_ZONE_PCT`, `ENVIRONMENT`, `EODHD_API_KEY`, `EODHD_API_TOKEN`, `ETHUSDT`, `EXECUTION_HIGH_ADX`, `EXECUTION_ROUTER_ENABLED`, `EXPECTED_WIN_RATE_MIN_COVERAGE`, `EXPECTED_WIN_RATE_MIN_TRACKED`
- `FCS_API_KEY`, `FCS_API_SECRET`, `FIB_TOUCH_TOLERANCE_PCT`, `FINNHUB_API_KEY`, `FMP_API_KEY`, `FORCE_SIGNAL_ASSETS`, `FORCE_SIGNAL_FETCH_TIMEOUT_SECONDS`, `FOREX_FACTORY_CALENDAR_URL`, `FREE_ASSET_COOLDOWN_HOURS`, `FREE_DIRECT_DISPATCH`
- `FREE_DISTRIBUTION_STARTUP_DELAY_SECONDS`, `FREE_FOMO_DISPATCH_ONLY`, `FROMSYMBOL`, `FX_DEFAULT_ENABLED`, `FX_PAIRS`, `FX_PREFERRED_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_API_TIMEOUT_SECONDS`, `GEMINI_DAILY_LIMIT`, `GEMINI_DAILY_REVIEW_ENABLED`
- `GEMINI_INLINE_MODEL`, `GEMINI_INLINE_TOP_N`, `GEMINI_MODEL`, `GEMINI_REVIEW_ENABLED`, `GEMINI_SENTIMENT_THRESHOLD`, `GEMINI_SIGNAL_REVIEW_MODEL`, `GEMINI_SIGNAL_REVIEW_TIMEOUT_SEC`, `HELP_MENU_CACHE_TTL_SECONDS`, `HOST`, `HTF_STRONG_CONFIDENCE`
- `HTF_WEAK_CONFIDENCE`, `HTTPS_PROXY`, `HTTP_PROXY`, `IMP_FX_ALLOWED_SESSIONS`, `INDEX_CLOSE_UTC`, `INDEX_DAILY_BREAK_UTC`, `INDEX_FRIDAY_CLOSE_HOUR_UTC`, `INDEX_MARKET_MODE`, `INDEX_OPEN_UTC`, `INDEX_PREFERRED_PROVIDER`
- `INDEX_SUNDAY_OPEN_HOUR_UTC`, `INDEX_TICKERS`, `INDEX_TRENDING_TOP_N`, `LASTUPDATE`, `LEADERBOARD_MIN_AVG_R`, `LEADERBOARD_MIN_TRACKED_TRADES`, `LEADERBOARD_MIN_WIN_RATE`, `LIFECYCLE_NOTIFICATION_RETRY_LIMIT`, `LIVE_PROVIDER_SMOKE_ASSETS`, `LOG_JSON`
- `LS_FX_ALLOWED_SESSIONS`, `MACRO_SNAPSHOT_REFRESH_SECONDS`, `MAKER_FEE_PCT`, `MARKETSTACK_API_KEY`, `MARKET_CHECK_INTERVAL_MINUTES`, `MARKET_CIRCUIT_BREAKER_TIMEOUT_SECONDS`, `MARKET_ENRICHMENT_TIMEOUT_SECONDS`, `MARKET_FETCH_ASSET_CONCURRENCY`, `MARKET_PROVIDER_TIMEOUT_SECONDS`, `MARKET_TIMEFRAME_FETCH_TIMEOUT_SECONDS`
- `MAX_ACTIVE_TRADES`, `MAX_CORRELATION`, `MAX_DAILY_LOSS`, `MAX_LEVERAGE`, `MAX_LIVE_RISK_PCT`, `MAX_MONTHLY_DRAWDOWN`, `MAX_PORTFOLIO_CORRELATION`, `MAX_RISK_PCT`, `MAX_RISK_PER_TRADE`, `MAX_TRADES_PER_DIRECTION`
- `META_API_DOMAIN`, `META_API_REGION`, `META_API_TOKEN`, `MIN_CANDLES_FOR_INDICATORS`, `MIN_RR_RATIO`, `MIN_RR_RISK`, `MIN_SCORE_CEILING`, `MIN_SCORE_FLOOR`, `MIN_SIGNALS_PER_CYCLE`, `MIN_SL_PCT`
- `ML_ARCHIVE_BACKFILL_ENABLED`, `ML_ARCHIVE_DB_TIMEOUT_SECONDS`, `ML_ARCHIVE_INTERVAL_MINUTES`, `ML_BASELINE_FEATURE_STATS_PATH`, `ML_CANDIDATE_MODEL_PATH`, `ML_CONFIDENCE_FACTOR_BASE`, `ML_CONFIDENCE_FACTOR_SCALE`, `ML_DRIFT_CHECK_INTERVAL_SECONDS`, `ML_DRIFT_CONFIDENCE_FLOOR`, `ML_DRIFT_CONFIDENCE_MULTIPLIER`
- `ML_DRIFT_MONITOR_ENABLED`, `ML_DRIFT_PSI_THRESHOLD`, `ML_DRIFT_RETRAIN_ON_DETECT`, `ML_ENABLED`, `ML_HARD_FILTER_MIN`, `ML_HIGH_CONFIDENCE`, `ML_LIVE_FEATURE_STATS_PATH`, `ML_MAX_RECORDS`, `ML_MEDIUM_CONFIDENCE`, `ML_MIN_LIVE_PROOF_ROWS`
- `ML_MIN_TRAIN_ROWS`, `ML_MODEL_PATH`, `ML_MODEL_RUNTIME_STATE_KEY`, `ML_MODEL_VERSION`, `ML_OFFLINE_BOOTSTRAP_ENABLED`, `ML_OFFLINE_BOOTSTRAP_ROWS`, `ML_OFFLINE_BOOTSTRAP_SEED`, `ML_PROB_THRESHOLD`, `ML_RECENCY_HALF_LIFE_DAYS`, `ML_REJECTION_THRESHOLD`
- `ML_RETRAIN_DAYS`, `ML_RETRAIN_INTERVAL_HOURS`, `ML_RETRAIN_LOOKBACK_DAYS`, `ML_RETRAIN_MIN_SAMPLES`, `ML_RISK_BASE`, `ML_RISK_HIGH_PCT`, `ML_RISK_LOW_PCT`, `ML_RISK_MEDIUM_PCT`, `ML_RISK_RANGE`, `ML_SHADOW_MODE`
- `ML_STRICT_SCHEMA`, `ML_TARGET_AUC`, `ML_THRESHOLD_DEFAULT`, `ML_THRESHOLD_MAX`, `ML_THRESHOLD_MIN`, `ML_THRESHOLD_MIN_OUTCOMES`, `ML_THRESHOLD_UPDATE_HOURS`, `ML_TRAIN_INTERVAL_SECONDS`, `ML_TRAIN_LOOKBACK_DAYS`, `ML_WEEKLY_RETRAIN_ENABLED`
- `ML_WEIGHTING_DB`, `MT5_ALLOW_LIVE_ACCOUNTS`, `MT5_EXECUTION_QUEUE_SIZE`, `MT5_EXECUTION_RETENTION_DAYS`, `NASDAQ_DATA_LINK_API_KEY`, `NASDAQ_DATA_LINK_DATASETS_JSON`, `NATIVE_MT5_DEVIATION_POINTS`, `NATIVE_MT5_MAX_SLIPPAGE_BPS`, `NEWSAPI_KEY`, `NEWS_API_KEY`
- `NEWS_MAX_EVENTS_PER_SYNC`, `NEWS_SYNC_INTERVAL_HOURS`, `NEWS_VOLATILITY_BUFFER_MULTIPLIER`, `NEWS_VOL_ADJ`, `NEWS_WINDOW_MINUTES`, `NO_CANDLE_LOG_COOLDOWN_SECONDS`, `NO_TRADE_BUFFER_MINUTES`, `OANDA_ACCOUNT_ID`, `OANDA_API_KEY`, `OANDA_PRACTICE`
- `OBS_VALUE`, `OHLC_INFLIGHT_WAIT_TIMEOUT_SECONDS`, `OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME`, `OHLC_PROVIDER_QUEUE_TIMEOUT_SECONDS`, `OHLC_PROVIDER_REQUEST_TIMEOUT_SECONDS`, `ONCHAIN_ALPHA_ENABLED`, `ONCHAIN_INFLOW_SPIKE`, `ONCHAIN_MIN_NET_FLOW`, `OPENAI_API_KEY`, `OPENAI_CODEX_REVIEW_MAX_TOKENS`
- `OPENAI_CODEX_REVIEW_MODEL`, `OPENAI_CODEX_REVIEW_TIMEOUT_SECONDS`, `OPENAI_MODEL`, `OPEN_SIGNALS_MAX_PER_ASSET`, `OPEN_SIGNALS_MAX_PER_CLASS`, `ORDER_BOOK_IMBALANCE_THRESHOLD`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SDK_DISABLED`, `OUTCOME_ACTIVE_SIGNAL_LIMIT`
- `OUTCOME_BACKFILL_LOOKBACK_HOURS`, `OUTCOME_BACKFILL_SIGNAL_LIMIT`, `OUTCOME_BROADCAST_ENABLED`, `OUTCOME_CATCHUP_LIMIT`, `OUTCOME_CATCHUP_MAX_AGE_DAYS`, `OUTCOME_CATCHUP_MIN_AGE_HOURS`, `OUTCOME_CHECK_INTERVAL_SECONDS`, `OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS`, `OUTCOME_FORCE_CLOSE_HOURS`, `OUTCOME_GLOBAL_ADMIN_OWNER_LIMIT`
- `OUTCOME_GLOBAL_FREE_LIMIT`, `OUTCOME_GLOBAL_PAID_LIMIT`, `OUTCOME_LIFECYCLE_ENABLED`, `OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS`, `OUTCOME_NOTIFICATION_STARTUP_DELAY_SECONDS`, `OUTCOME_NOTIFICATION_START_DELAY_SECONDS`, `OUTCOME_QUOTE_MAX_CONCURRENCY`, `OUTCOME_QUOTE_TIMEOUT_SECONDS`, `OUTCOME_SCAN_LIMIT`, `OUTCOME_SCAN_MAX_AGE_DAYS`
- `OUTCOME_SNAPSHOT_STALE_SECONDS`, `OUTCOME_SNAPSHOT_TTL_SECONDS`, `OUTCOME_TIME_STOP_HOURS`, `OUTCOME_TRACKER_MAX_CONCURRENCY`, `OUTCOME_TRACKER_ML_RETRAIN_INTERVAL_SECONDS`, `OUTCOME_TRACKER_UPDATE_USER_PERF`, `OUTCOME_TRACK_DELIVERED_ONLY`, `OWNER_ADMIN_BYPASS_DELIVERY_DEDUPE`, `OWNER_ASSET_COOLDOWN_HOURS`, `OWNER_IDS`
- `OWNER_TELEGRAM_ID`, `PAYMENTS_ENABLED`, `PAYMENTS_PUBLIC_ENABLED`, `PAYSTACK_BASE_URL`, `PAYSTACK_CALLBACK_URL`, `PAYSTACK_CANCEL_RETRY_ATTEMPTS`, `PAYSTACK_SECRET_KEY`, `PAYSTACK_WEBHOOK_IP_WHITELIST`, `PAYSTACK_WEBHOOK_SECRET`, `PERFORMANCE_BASELINE_VERSION`
- `PGDATABASE`, `PGHOST`, `PGPASSWORD`, `PGPORT`, `PGSSLMODE`, `PGUSER`, `PINECONNECTOR_LICENSE_ID`, `PINECONNECTOR_RISK_PCT`, `PINECONNECTOR_WEBHOOK_URL`, `POLYGON_API_KEY`
- `PORT`, `PORTFOLIO_EXPOSURE_FAIL_OPEN`, `PORTFOLIO_EXPOSURE_REQUIRE_DELIVERED`, `POSITION_SIZE_ENFORCE_ASSET_CAPS`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_USER`, `PREMIUM_ASSET_COOLDOWN_HOURS`
- `PREMIUM_DAILY_EXECUTIONS`, `PREMIUM_MAX_LOT`, `PREMIUM_MONTHLY_PRICE_NGN`, `PREMIUM_PRICE_NGN`, `PREMIUM_PRICE_USD`, `PREMIUM_QUARTERLY_PRICE_NGN`, `PREMIUM_SCORE_THRESHOLD`, `PREMIUM_SCORE_THRESHOLD_FORCE`, `PREMIUM_YEARLY_PRICE_NGN`, `PRICE`
- `PRODUCTION_HEALTH_REQUIRE_DISTINCT_REDIS`, `PROFILE_DEBUG_DB_TIMEOUT_SECONDS`, `PROVIDER_COOLDOWN_SECONDS`, `PROVIDER_FAILURE_THRESHOLD`, `PROVIDER_HEALTH_REDIS_HASH`, `PROVIDER_OUTAGE_ALERT_INTERVAL_MINUTES`, `PROVIDER_OUTAGE_ALERT_OPTIONAL`, `PROVIDER_OUTAGE_ALERT_SCHEDULE_MINUTES`, `PROVIDER_OUTAGE_MINUTES`, `PROVIDER_OUTAGE_OPTIONAL_PROVIDERS`
- `PROXY_API_PROVIDER_URL`, `PROXY_LIST`, `PUBLIC_BASE_URL`, `PUBLIC_TESTING_MODE`, `PYTHONPATH`, `QUALITY_FX_ALLOWED_TIMEFRAMES`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_GIT_COMMIT_SHA`
- `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_SERVICE`, `RAILWAY_SERVICE_NAME`, `RAILWAY_STATIC_URL`, `RAW`, `REAL_EXECUTION_ENABLED`, `REDIS_MAX_CONNECTIONS`, `REDIS_PRIVATE_URL`, `REDIS_URL`, `REDIS_WEBHOOK_QUEUE_MAX_DEPTH`
- `REFERRAL_BONUS_DAYS`, `REFERRAL_MONTHLY_CAP_DAYS`, `REFRESH_ACTIVE_SIGNAL_LIMIT`, `REGIME_ADX_RANGING`, `REGIME_ADX_THRESHOLD`, `REGIME_ADX_TREND`, `REGIME_ATR_VOLATILE`, `REGIME_BB_RANGING`, `REGIME_CACHE_TTL_SECONDS`, `REGIME_STRATEGIES`
- `REGIME_STRATEGIES_JSON`, `REJECTION_DB_BATCH_SIZE`, `REJECTION_DB_FLUSH_SECONDS`, `REJECTION_DB_TIMEOUT_SECONDS`, `REJECTION_DECISION_LOOKBACK_DAYS`, `REJECTION_LOG_WRITE_ENABLED`, `REJECTION_SPOOL_MAX_ITEMS`, `REJECT_OUTCOME_MIN_TRACK_AGE_MINUTES`, `REJECT_OUTCOME_MOVE_PCT`, `REJECT_OUTCOME_WINDOWS`
- `REJECT_OUTCOME_WINDOWS_HOURS`, `REQUIRE_DISTINCT_DELIVERY_REDIS`, `RESEND_INCLUDE_FREE`, `RESEND_JOB_LOCK_ID`, `RESEND_MAX_SIGNALS`, `RESEND_MIN_SCORE`, `RESEND_START_DELAY_SECONDS`, `RESEND_UNSENT_INTERVAL_SECONDS`, `RESEND_UNSENT_STARTUP_DELAY_SECONDS`, `RESOURCE_GOVERNOR_STATE`
- `RESOURCE_PRESSURE_LEVEL`, `RISK_FREE_USER_COOLDOWN_SECONDS`, `RISK_PER_TRADE_PCT`, `RISK_SUGGESTION_BASE_MULT`, `RISK_SUGGESTION_MODERATE_MULT`, `RISK_SUGGESTION_STRONG_MULT`, `RUN_DB_MIGRATIONS_AT_BOOT`, `RUN_ENGINE_LOOP`, `RUN_LIVE_DATA_TESTS`, `RUN_MODE`
- `RUN_WORKER_LOOP`, `SCHEDULER_LEASE_CONNECT_TIMEOUT_SECONDS`, `SCHEDULER_LEASE_HEALTH_SECONDS`, `SCHEDULER_LEASE_LOCK_ID`, `SCHEDULER_LEASE_RETRY_SECONDS`, `SCHEDULER_OWNER`, `SCHEDULER_OWNER_ROLE`, `SCORE_DISPLAY_MAX`, `SCORE_SOFT_CAP_CEILING`, `SCORE_SOFT_CAP_KNEE`
- `SCORE_SOFT_CAP_SCALE`, `SENTIMENT_ROLLOUT_PHASE`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_URL`, `SERVICE_ROLE`, `SHADOW_PRICE_CONCURRENCY`, `SHADOW_TRACKER_BATCH_SIZE`, `SHADOW_TRACKER_INTERVAL_SECONDS`
- `SIGNALRANK_DISABLE_BACKGROUND_THREADS`, `SIGNALRANK_RESOURCE_PRESSURE`, `SIGNALRANK_STATE_REDIS_URL`, `SIGNALRANK_TEST_PYDEPS`, `SIGNALS_COMMAND_DB_TIMEOUT_SECONDS`, `SIGNAL_DEDUP_BLOCK_ORPHAN_ACTIVE_TRADE`, `SIGNAL_DEDUP_CROSS_TIMEFRAME`, `SIGNAL_DEDUP_DECAY_HOURS`, `SIGNAL_DEDUP_ENTRY_SIMILARITY_PCT`, `SIGNAL_DEDUP_HARD_WINDOW_HOURS`
- `SIGNAL_DEDUP_HOURS`, `SIGNAL_DEDUP_SIMILARITY_THRESHOLD`, `SIGNAL_ENTRY_GATING_ENABLED`, `SIGNAL_STORE_RETRY_ATTEMPTS`, `SIGNAL_STORE_TIMEOUT_SECONDS`, `SIGNAL_TIMEZONE_DISPLAY_ENABLED`, `SIGNAL_UPDATE_MIN_ML_DELTA`, `SIGNAL_UPDATE_MIN_NEWS_DELTA`, `SIGNAL_UPDATE_MIN_ROI_DELTA`, `SIGNAL_UPDATE_MIN_RR_DELTA`
- `SLIPPAGE_TOLERANCE`, `SMART_DCA_QUOTE_TIMEOUT_SECONDS`, `SMART_EXIT_BTC_CRASH_PCT`, `SMART_EXIT_MAX_SL_SHARE`, `SMART_EXIT_MIN_CONFLUENCE_VOTES`, `SMART_EXIT_MIN_LOSS_PCT`, `SQUEEZE_FUNDING_THRESHOLD`, `STALE_PRICE_FETCH_TIMEOUT`, `STALE_PRICE_THRESHOLD_PCT`, `STARTUP_MAINTENANCE_TIMEOUT_SECONDS`
- `STARTUP_OPS_TIMEOUT_SECONDS`, `STARTUP_OPS_WAIT_FOR_MAINTENANCE_SECONDS`, `START_TS`, `STATE_CACHE_MAX_KEYS`, `STATE_FLUSH_INTERVAL_SECONDS`, `STATE_REDIS_URL`, `STOCK_CLOSE_UTC`, `STOCK_OPEN_UTC`, `STOCK_PREFERRED_PROVIDER`, `STOCK_TICKERS`
- `STOCK_TRENDING_TOP_N`, `STOP_LOSS_PCT`, `STRATEGY_DRAWDOWN_DISABLE_LIST`, `STRATEGY_WEIGHTS`, `STRATEGY_WEIGHTS_JSON`, `TAKER_FEE_PCT`, `TARGET_AVG_R`, `TARGET_WIN_RATE`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BROADCAST_RPS`
- `TELEGRAM_DELETE_WEBHOOK_ON_SHUTDOWN`, `TELEGRAM_GLOBAL_SEND_DELAY_SECONDS`, `TELEGRAM_OWNER_ID`, `TELEGRAM_RETRY_AFTER_MAX_SECONDS`, `TELEGRAM_RICH_MESSAGES_ENABLED`, `TELEGRAM_SEND_MAX_ATTEMPTS`, `TELEGRAM_UPDATES_CONSUMER_GROUP`, `TELEGRAM_UPDATES_DLQ_STREAM`, `TELEGRAM_UPDATES_QUEUE_KEY`, `TELEGRAM_UPDATES_STREAM`
- `TELEGRAM_USE_WEBHOOK`, `TELEGRAM_WEBHOOK_SECRET`, `TERMS_BLAST_ON_DEPLOY`, `THRESHOLD_ANALYSIS_INTERVAL_HOURS`, `THRESHOLD_MIN_SAMPLES`, `TICK_INTERVAL_SECONDS`, `TIINGO_API_KEY`, `TIMEZONE_STORE_LOCATION_COORDINATES`, `TIME_PERIOD`, `TOSYMBOL`
- `TP_RETRACE_MIN_ML_CONF`, `TP_RETRACE_SL_ZONE_PCT`, `TRACK_RECORD_DB`, `TRADABLE_ASSETS`, `TRADE_COOLDOWN_MINUTES`, `TRADE_MGR_CHECK_INTERVAL`, `TRADE_MGR_SPREAD_MULT`, `TRADIER_BASE_URL`, `TRADIER_TOKEN`, `TRADINGVIEW_BROKER`
- `TRADINGVIEW_COMMODITY_PREFIX`, `TRADINGVIEW_ENRICHMENT_TIMEOUT_SECONDS`, `TRADINGVIEW_FX_PREFIX`, `TRADINGVIEW_INDEX_PREFIX`, `TRADINGVIEW_STOCK_PREFIX`, `TRAILING_ACTIVATION_MODE`, `TRAILING_STOP_ATR_MULT`, `TRAINING_R_CLIP_MAX`, `TRAINING_R_CLIP_MIN`, `TRAVEL_TIMEZONE_REFRESH_DAYS`
- `TV_WEBHOOK_SECRET`, `TWELVEDATA_API_KEY`, `TWITTER_BEARER_TOKEN`, `TYPE`, `USD`, `USDT`, `USER_TIER_CACHE_TTL_SECONDS`, `USE_MULTI_PROVIDER_DATA`, `UVICORN_LOG_LEVEL`, `VIP_ASSET_COOLDOWN_HOURS`
- `VIP_MAX_CAPACITY`, `VIP_MAX_LOT`, `VIP_MONTHLY_PRICE_NGN`, `VIP_PRICE_NGN`, `VIP_PRICE_USD`, `VIP_SEAT_LIMIT`, `VOLATILITY_WIDEN_ATR_MULT`, `VOLATILITY_WIDEN_SL_MULT`, `VOLATILITY_WIDEN_TP_MULT`, `WAITLIST_DB_TIMEOUT_SECONDS`
- `WEBHOOK_DOMAIN`, `WEBHOOK_HARD_TIMEOUT_SECONDS`, `WEBHOOK_MAX_BODY_BYTES`, `WEBHOOK_MAX_RETRY`, `WEBHOOK_REDIS_QUEUE_ENABLED`, `WEBHOOK_SECRET`, `WEBHOOK_SOFT_TIMEOUT_SECONDS`, `WEBHOOK_TIMEOUT_SECONDS`, `WEBHOOK_UPDATE_QUEUE_SIZE`, `WEBHOOK_UPDATE_WORKERS`
- `WEBHOOK_URL`, `WEB_SECRET_KEY`, `WEEKLY_PLAN`, `WORKER_ENGINE_PULSE_ENABLED`, `WORKER_HEARTBEAT_INTERVAL_SECONDS`, `WORKER_OUTCOME_TRACKER_ENABLED`, `WS_INGEST_ENABLED`, `XGBOOST_MODEL_PATH`, `XGB_NTHREAD`, `X_BEARER_TOKEN`
- `YFINANCE_COOLDOWN_SECONDS`, `YFINANCE_STALENESS_GRACE_SECONDS`, `YFINANCE_TIMEOUT_SECONDS`

## 29.7 Full production-runtime file inventory

Every path below requires a preserve/reimplement/deprecate disposition and traceability to the new repository:

- `FIX_INTEGRATION_GUIDE.py` — lines=198; symbols=none
- `IMPLEMENTATION_FIX_PLAN.py` — lines=325; symbols=none
- `IMPLEMENTATION_TODO.py` — lines=62; symbols=none
- `RESTORE_THRESHOLDS_FIX.py` — lines=295; symbols=apply_fix
- `SET_THRESHOLDS_FIX.py` — lines=35; symbols=main
- `SIGNALRANKAI_COMMAND_FIX.py` — lines=105; symbols=on_startup_complete
- `SIGNAL_SPAM_FIX_STandalone.py` — lines=174; symbols=GenerationCooldown, check_generation_cooldown, get_generation_cooldown, get_generation_cooldown_remaining, record_signal_generated
- `STRATEGY_DEBUG_FIX.py` — lines=240; symbols=diagnose_strategy_failure, force_emergency_signals, get_emergency_signals
- `admin/auto_kill.py` — lines=154; symbols=daily_loss, evaluate_system_health, halt_system, is_system_halted, monthly_drawdown, notify_owner
- `admin/kill_switch.py` — lines=5; symbols=check_system
- `apply_fix.py` — lines=46; symbols=apply_fix
- `check_command_access.py` — lines=11; symbols=none
- `config.py` — lines=345; symbols=Config, database_url_candidates, prefer_ipv4_database_url, resolve_database_url
- `conftest.py` — lines=42; symbols=pytest_collection_modifyitems, pytest_ignore_collect
- `core/agent_council.py` — lines=89; symbols=AgentSpec, CouncilMode, council_manifest, get_agent
- `core/asset_registry.py` — lines=171; symbols=AssetSpec, canonicalize_asset, get_asset_spec, list_asset_specs, resolve_asset_spec
- `core/automaton.py` — lines=107; symbols=AutomatonDecision, AutomatonInputs, AutomatonState, evaluate, starting_balance, status
- `core/circuit_breaker.py` — lines=80; symbols=CircuitBreaker, CircuitConfig, get_provider_breaker_snapshot, provider_breaker
- `core/codexops.py` — lines=50; symbols=AuditFinding, CodexOpsMode, audit_text, mode
- `core/command_limits.py` — lines=99; symbols=check_gemini_audit_rate_limit, get_gemini_audit_limit, get_gemini_audit_remaining, increment_gemini_audit_counter
- `core/env.py` — lines=115; symbols=Environment, SafetyFlags, env_bool, env_int, environment, redact_value, secret_present, validate_required_secrets
- `core/event_bus.py` — lines=378; symbols=EventBus, EventBusAdapter, EventSubscriber, publish_signal_delivered, publish_signal_failed, publish_signal_ready
- `core/event_types.py` — lines=64; symbols=none
- `core/evolution_agent.py` — lines=242; symbols=EvolutionAgent
- `core/feature_flags.py` — lines=64; symbols=FeatureFlag, FeatureState, get_feature, is_available
- `core/paper_ledger.py` — lines=616; symbols=PaperLedger, PaperPosition, get_paper_ledger, sync_execution
- `core/patch_manager.py` — lines=142; symbols=PatchManager
- `core/performance.py` — lines=108; symbols=PerformanceTracker, avg_reward_risk, dynamic_weight, strategy_stats
- `core/redis_cache.py` — lines=145; symbols=cache_get, cache_key, cache_market_data, cache_news_sentiment, cache_set, cache_signal, cache_stats, cache_user_prefs, cached_market_data...
- `core/redis_global_stats.py` — lines=348; symbols=RedisGlobalStats, StatsAdapter
- `core/redis_state.py` — lines=1157; symbols=KillSwitchState, RedisState, get_delivered_signals_sync, mark_signal_delivered_sync, redis_state_diagnostics, was_signal_delivered_sync
- `core/redis_streams.py` — lines=435; symbols=EnqueueResult, RecoverableStream, StreamMessage, stream_consumer_name, telegram_update_stream
- `core/release_guard.py` — lines=216; symbols=GuardCheck, ReleaseReport, evaluate_release, public_test_status
- `core/resource_governor.py` — lines=1008; symbols=DegradationPolicy, MemoryLimit, ResourceGovernor, ResourceInputs, ResourceSnapshot, ResourceState, ResourceThresholds, detect_memory_limi...
- `core/security.py` — lines=58; symbols=api_token_pepper, constant_time_equal, fingerprint, redact_secrets
- `core/settings.py` — lines=93; symbols=Settings, get_settings, validate_required_settings
- `core/signal_governor.py` — lines=18; symbols=can_send_signal, record_signal_sent
- `core/signal_lifecycle.py` — lines=204; symbols=SignalLifecycle, event_transition_allowed, highest_tp_for_state, lifecycle_state_for_event, lifecycle_state_for_outcome, lifecycle_transi...
- `core/telemetry.py` — lines=201; symbols=init_tracer, observe_engine_cycle, observe_engine_task, observe_http_request, observe_ml_confidence, observe_signal_dispatch, observe_sig...
- `core/tier_constants.py` — lines=235; symbols=get_daily_limit, get_min_score, has_feature, normalize_tier, tier_rank
- `core/tier_policy.py` — lines=535; symbols=AccessDecision, Tier, TierEntitlements, button_action_name, evaluate_button_access, evaluate_command_access, evaluate_feature_access, get...
- `core/trade_tracker.py` — lines=691; symbols=TradeRecord, add_trade, close_trade, open_trades, price_hit_sl, price_hit_tp, update_trade_outcomes
- `core/validators.py` — lines=29; symbols=validate_candles
- `core/version.py` — lines=32; symbols=get_version_banner
- `data/alternative_providers.py` — lines=117; symbols=fetch_cryptoquant_context, fetch_glassnode_context, fetch_onchain_context
- `data/binance_ws.py` — lines=131; symbols=build_streams, iter_events
- `data/connector_registry.py` — lines=294; symbols=get_async_providers_for_asset, get_providers_for_asset
- `data/connectors/__init__.py` — lines=55; symbols=none
- `data/connectors/alpaca_adapter.py` — lines=82; symbols=get_candles
- `data/connectors/alphavantage_adapter.py` — lines=19; symbols=get_candles
- `data/connectors/base.py` — lines=7; symbols=Connector
- `data/connectors/binance_adapter.py` — lines=119; symbols=get_candles
- `data/connectors/bybit_adapter.py` — lines=88; symbols=get_candles
- `data/connectors/coinbase_adapter.py` — lines=91; symbols=get_candles
- `data/connectors/cryptocompare_adapter.py` — lines=155; symbols=cryptocompare_get_candles, cryptocompare_get_candles_sync
- `data/connectors/deribit_adapter.py` — lines=121; symbols=get_candles
- `data/connectors/ecb_adapter.py` — lines=83; symbols=get_candles
- `data/connectors/eodhd_adapter.py` — lines=100; symbols=get_candles
- `data/connectors/fcs_adapter.py` — lines=209; symbols=get_candles
- `data/connectors/finnhub_adapter.py` — lines=95; symbols=get_candles
- `data/connectors/fmp_adapter.py` — lines=157; symbols=get_candles
- `data/connectors/kraken_adapter.py` — lines=88; symbols=get_candles
- `data/connectors/kucoin_adapter.py` — lines=147; symbols=get_candles
- `data/connectors/marketstack_adapter.py` — lines=84; symbols=get_candles
- `data/connectors/nasdaq_data_link_adapter.py` — lines=81; symbols=get_candles
- `data/connectors/oanda_adapter.py` — lines=19; symbols=get_candles
- `data/connectors/okx_adapter.py` — lines=98; symbols=get_candles
- `data/connectors/polygon_adapter.py` — lines=84; symbols=get_candles
- `data/connectors/stooq_adapter.py` — lines=66; symbols=get_candles
- `data/connectors/tiingo_adapter.py` — lines=174; symbols=get_candles
- `data/connectors/tradier_adapter.py` — lines=73; symbols=get_candles
- `data/connectors/twelvedata_adapter.py` — lines=75; symbols=get_candles
- `data/connectors/yfinance_adapter.py` — lines=106; symbols=get_candles
- `data/cryptocompare_ws.py` — lines=151; symbols=build_subs, iter_events
- `data/dynamic_symbol_assign.py` — lines=341; symbols=detect_asset_type, format_symbol, format_symbol_for_binance, format_symbol_for_cryptocompare, format_symbol_for_oanda, format_symbol_for_...
- `data/fetcher.py` — lines=2649; symbols=async_get_candles, consume_provider_recovery_alerts, discover_tradingview_symbols, fetch_market_data, get_asset_type, get_candles, get_cr...
- `data/fetcher_router.py` — lines=283; symbols=DataRouter, fetch_candles, get_router
- `data/get_live_price.py` — lines=1054; symbols=PriceCircuitBreaker, PriceCircuitConfig, get_cached_price, get_circuit_breaker_status, get_live_price, get_live_price_quote, get_live_pri...
- `data/indicator_schema.py` — lines=48; symbols=missing_indicators, normalize_indicator_schema
- `data/indicators.py` — lines=437; symbols=ADX, ADX_with_DI, ATR, BOLLINGER_BANDS, MACD, OBV, RSI, STOCH_RSI, calculate_indicators, classify_volatility, detect_breakout, detect_hig...
- `data/market_data.py` — lines=1292; symbols=count_usable_market_data_assets, detect_order_blocks, fetch_candles_with_circuit_breaker, fetch_market_data_cached, format_ticker, get_re...
- `data/market_hours.py` — lines=499; symbols=MarketSessionStatus, get_asset_class, get_market_session_status, is_commodity_holiday, is_fx_holiday, is_fx_low_liquidity, is_market_open...
- `data/news.py` — lines=219; symbols=fetch_news_headlines, get_news_sentiment, simple_sentiment_score
- `data/pair_discovery.py` — lines=694; symbols=get_all_tradable_assets, get_all_trending_pairs, get_asset_discovery_snapshot, get_latest_asset_universe, get_trending_commodity_tickers,...
- `data/provider_catalog.py` — lines=378; symbols=CertificationStatus, ProviderSpec, get_provider_spec, list_provider_specs, providers_for_asset_class, validate_candles
- `data/provider_types.py` — lines=310; symbols=BreakerState, FinalQuotePolicy, LivePriceFailure, LivePriceQuote, ProviderHealthState, QuoteKind, QuoteTrustDecision, normalize_asset_cla...
- `data/providers.py` — lines=1038; symbols=fetch_alphavantage_candles, fetch_binance_ccxt_candles, fetch_candles_waterfall, fetch_coingecko_candles, fetch_coingecko_market_chart, f...
- `data/startup_selfcheck.py` — lines=211; symbols=check_alphavantage, check_binance, run_startup_data_selfcheck
- `data/symbol_formatter.py` — lines=266; symbols=format_symbol_for_alphavantage, format_symbol_for_oanda, format_symbol_for_polygon, format_symbol_for_twelvedata, format_symbol_for_yahoo...
- `data/ws_ingest.py` — lines=545; symbols=run_ws_ingestor
- `db/access.py` — lines=99; symbols=has_full_access, is_owner, owner_id, resolve_user_tier
- `db/auto_ops.py` — lines=485; symbols=run_startup_ops
- `db/database.py` — lines=43; symbols=create_engine, get_database_url, get_database_url_or_none
- `db/features/__init__.py` — lines=1; symbols=none
- `db/features/performance.py` — lines=48; symbols=segment_summaries, summarize_rows
- `db/market_cache.py` — lines=160; symbols=get_recent_candles, prune_old_candles, upsert_market_candle, upsert_market_tick
- `db/migrations/env.py` — lines=76; symbols=get_url, run_migrations_offline, run_migrations_online
- `db/migrations/versions/0001_init.py` — lines=132; symbols=downgrade, upgrade
- `db/migrations/versions/0002_features.py` — lines=151; symbols=downgrade, upgrade
- `db/migrations/versions/0003_runtime_state.py` — lines=35; symbols=downgrade, upgrade
- `db/migrations/versions/0004_payment_events.py` — lines=45; symbols=downgrade, upgrade
- `db/migrations/versions/0005_bot_events.py` — lines=37; symbols=downgrade, upgrade
- `db/migrations/versions/0006_bigint_telegram_ids.py` — lines=51; symbols=downgrade, upgrade
- `db/migrations/versions/0007_market_data_cache.py` — lines=54; symbols=downgrade, upgrade
- `db/migrations/versions/0008_user_tier_column.py` — lines=31; symbols=downgrade, upgrade
- `db/migrations/versions/0009_archived_column.py` — lines=31; symbols=downgrade, upgrade
- `db/migrations/versions/0010_consolidate_full_schema.py` — lines=331; symbols=downgrade, upgrade
- `db/migrations/versions/0011_platform_hardening_security_scaling.py` — lines=122; symbols=downgrade, upgrade
- `db/migrations/versions/0012_outcome_notify_state.py` — lines=103; symbols=downgrade, upgrade
- `db/migrations/versions/0013_proxy_nodes.py` — lines=44; symbols=downgrade, upgrade
- `db/migrations/versions/0014_add_outcome_pnl_pct.py` — lines=39; symbols=downgrade, upgrade
- `db/migrations/versions/0015_active_signal_guard.py` — lines=195; symbols=downgrade, upgrade
- `db/migrations/versions/0016_signal_profile_metadata.py` — lines=32; symbols=downgrade, upgrade
- `db/migrations/versions/0017_signal_delivery_proof.py` — lines=47; symbols=downgrade, upgrade
- `db/migrations/versions/0018_signal_lifecycle_events.py` — lines=82; symbols=downgrade, upgrade
- `db/migrations/versions/0019_user_timezone_privacy.py` — lines=41; symbols=downgrade, upgrade
- `db/migrations/versions/0020_payment_receipts.py` — lines=42; symbols=downgrade, upgrade
- `db/migrations/versions/0021_runtime_truth_hardening.py` — lines=34; symbols=downgrade, upgrade
- `db/migrations/versions/0022_active_guard_reconcile.py` — lines=175; symbols=downgrade, upgrade
- `db/models.py` — lines=739; symbols=ActiveSignalMessage, AdminEvent, AlertPreference, ApiToken, AssetLiveMetric, Base, BotEvent, DecisionLog, EconomicEvent, FreeSignalQueue,...
- `db/mt5_models.py` — lines=447; symbols=MT5Account, MT5ExecutionLog, MT5Position, close_execution, create_mt5_account, get_account_by_id, get_default_account, get_open_execution...
- `db/pg_compat.py` — lines=155; symbols=get_all_user_ids_compat, postgres_enabled, store_signal_compat
- `db/pg_features.py` — lines=3679; symbols=SignalDedupBlocked, acquire_signal_lock, active_signal_exists, add_managed_asset, archive_signal_after_outcome, check_active_signal_exist...
- `db/priority.py` — lines=188; symbols=DBAdmissionController, DBPriority
- `db/repository.py` — lines=491; symbols=activate_subscription, count_active_subscriptions, count_active_vip_users, create_api_token, expire_subscriptions, get_active_subscriptio...
- `db/session.py` — lines=1207; symbols=AnalyticsWorkDeferred, DatabaseWorkDeferred, NoncriticalWriteDropped, async_session, collect_database_health, create_engine, create_sessi...
- `db/user_preferences.py` — lines=341; symbols=UserPreferencesManager, UserTradingPreferences, get_user_preferences, set_user_execution_mode, set_user_trading_mode, update_user_prefere...
- `delivery/__init__.py` — lines=13; symbols=none
- `delivery/fanout.py` — lines=55; symbols=DeliveryBatch, delivery_shard, iter_delivery_batches
- `delivery/receipts.py` — lines=185; symbols=DeliveryReceipt, ReceiptStore
- `delivery/service.py` — lines=201; symbols=DeliveryOperation, DeliveryState, TelegramDeliveryAmbiguous, canonical_delivery_state, forbids_blind_retry, is_ambiguous_send_error, is_s...
- `delivery/worker.py` — lines=129; symbols=delivery_receipt_reconciler_loop, reconcile_delivery_receipt, reconcile_delivery_receipts_once, start_delivery_receipt_reconciler, stop_d...
- `diagnostic_check.py` — lines=66; symbols=main
- `engine/admin_pulse.py` — lines=735; symbols=compute_engine_health, send_admin_pulse_via_telegram, send_weekly_filter_efficacy_via_telegram, start_pulse_loop
- `engine/advanced_exit_manager.py` — lines=353; symbols=AdvancedExitManager, ExitStrategy
- `engine/advanced_filters.py` — lines=452; symbols=ChopFilter, CorrelationClusterFilter, FakeBreakoutDetector, LiquiditySweepDetector, LowVolatilityFilter, NewsFilter, OverextendedFilter, ...
- `engine/ai_coach.py` — lines=270; symbols=AICoach, TradeAnalysis, format_coach, get_ai_coach
- `engine/analytics.py` — lines=484; symbols=AnalyticsTracker, ExcursionCalculator, RegimeAnalytics, calculate_mfe_mae, get_regime_analytics
- `engine/auto_optimizer.py` — lines=237; symbols=AutoOptimizerRunner, OptimizationResult, get_runner, run_optimization
- `engine/backtest.py` — lines=416; symbols=BacktestEngine, BacktestRunner, OptimizationEngine
- `engine/confluence_engine.py` — lines=446; symbols=run_confluence_engine
- `engine/consensus.py` — lines=190; symbols=best_signal_in_group, consensus_filter, contains_required_groups, group_by_asset_and_direction, unique_strategy_groups
- `engine/core.py` — lines=4741; symbols=load_tradable_assets, main_loop, start_outage_alert_job
- `engine/correlation_engine.py` — lines=373; symbols=CorrelationEngine, SignalExposure, check_correlation_allowed, clear_expired_signals, get_correlation_engine, get_exposure_summary, regist...
- `engine/correlation_filter.py` — lines=348; symbols=PortfolioExposureManager, cluster_key, select_best_per_cluster
- `engine/correlation_guard.py` — lines=278; symbols=CorrelationManager, PortfolioCorrelationGuard, check_and_veto, get_guard, get_manager
- `engine/cycle_queue.py` — lines=197; symbols=AssetCycleQueue
- `engine/dedup_wrapper.py` — lines=257; symbols=filter_duplicate_signals, get_dedup_stats, mark_signal_generated, mark_signals_generated, should_skip_signal
- `engine/delivery_freshness.py` — lines=817; symbols=DeliveryFreshnessResult, evaluate_signal_age, evaluate_time_to_telegraph, fetch_trusted_live_quote, max_delivery_age_minutes, validate_de...
- `engine/demo_runner.py` — lines=15; symbols=demo_run
- `engine/derivatives.py` — lines=273; symbols=SqueezeDetector, check_veto, get_squeeze_bias
- `engine/dynamic_threshold.py` — lines=92; symbols=calculate_dynamic_threshold, get_ml_model_auc, get_threshold
- `engine/endgame_integration.py` — lines=169; symbols=enrich_signal_execution, format_execution_info, get_endgame_status
- `engine/execution_router.py` — lines=174; symbols=SmartRouter, get_execution_strategy, get_router
- `engine/exit_manager.py` — lines=311; symbols=ExitManager, PartialExitTracker
- `engine/expectancy_gate.py` — lines=129; symbols=expectancy_gate, get_live_expectancy, global_expectancy_check, validate_expectancy_pipeline
- `engine/fee_manager.py` — lines=258; symbols=FeeManager, HighWaterMark, SubscriptionTier, calculate_performance_fee, format_all_fees, get_fee_manager
- `engine/filters.py` — lines=343; symbols=MarketRegimeFilter, SignalFilter, SlippageControl
- `engine/loop.py` — lines=308; symbols=demo_start, main_loop, run_once, start_engine_loop
- `engine/market_circuit_breaker.py` — lines=327; symbols=MarketCircuitBreaker, check_market_health, get_status, is_halted
- `engine/market_state.py` — lines=100; symbols=get_market_state, get_market_state_async, get_market_state_sync
- `engine/microstructure.py` — lines=253; symbols=OrderBookAnalyzer, check_order_book
- `engine/ml.py` — lines=592; symbols=adjust_weight_based_on_performance, disable_strategies_with_drawdown, get_live_strategy_weight, get_regime_strategies, get_strategy_weigh...
- `engine/ml_logger.py` — lines=263; symbols=get_pending_training_signals, get_training_data_count, log_ml_prediction, log_ml_training_data
- `engine/ml_weighting.py` — lines=702; symbols=MLWeightingLayer, StrategyPerformance, StrategyRecord, get_ml_weighting_layer, get_recommended_strategy, get_strategy_weights, record_str...
- `engine/mtf_analysis.py` — lines=251; symbols=MultiTimeframeAnalyzer, detect_htf_bias_flip
- `engine/news_filter.py` — lines=345; symbols=NewsKillswitch, check_trade_allowed, is_market_volatile
- `engine/off_market.py` — lines=59; symbols=OffMarketDecision, off_market_decision
- `engine/onchain_alpha.py` — lines=155; symbols=OnChainAlpha, check_veto, get_alpha
- `engine/outcome_eligibility.py` — lines=122; symbols=OutcomeEligibility, evaluate_outcome_eligibility
- `engine/outcome_snapshots.py` — lines=276; symbols=OutcomeSnapshot, build_outcome_snapshot, format_outcome_snapshot, read_cached_outcome_snapshot, read_outcome_snapshot, write_outcome_snap...
- `engine/performance_truth.py` — lines=23; symbols=none
- `engine/portfolio_intelligence.py` — lines=320; symbols=PortfolioIntelligence, PortfolioSummary, Position, format_portfolio, get_portfolio_intelligence
- `engine/price_fetcher.py` — lines=508; symbols=PriceBreakerConfig, PriceCircuitBreaker, get_asset_class, get_live_price, get_live_price_batch, get_price_breaker_status, get_routing_pro...
- `engine/price_validator.py` — lines=411; symbols=check_sl_tp_hit, enrich_signal_with_live_price, filter_stale_signals, get_asset_type, get_current_price, is_signal_fresh, is_signal_stale...
- `engine/public_track_record.py` — lines=389; symbols=AssetClassStats, PerformanceStats, PublicTrackRecord, TrackRecord, format_track_record, get_public_track_record, record_trade_result
- `engine/ranking.py` — lines=444; symbols=calculate_confidence_components, rank_signals
- `engine/realtime_outcome_tracker.py` — lines=1826; symbols=OutcomePriceObservation, RealtimeOutcomeTracker, SignalState, TrackedSignal, evaluate_tick, state_to_db_outcome
- `engine/referral_manager.py` — lines=143; symbols=ReferralManager
- `engine/regime.py` — lines=399; symbols=Regime, RegimeDetector, detect_market_regime, detect_regime, is_strategy_allowed
- `engine/regime_filter.py` — lines=176; symbols=MarketRegimeFilter, calculate_adx_from_candles, check_regime_filter
- `engine/rejection_learning.py` — lines=123; symbols=persist_rejected_signal_learning, schedule_rejected_signal_learning
- `engine/risk.py` — lines=877; symbols=best_target_for_direction, calculate_dynamic_risk, calculate_position_size, calculate_position_size_by_asset_class, calculate_stop_loss_b...
- `engine/risk_analytics.py` — lines=78; symbols=monte_carlo_monthly_projection, sharpe_ratio, sortino_ratio
- `engine/risk_manager.py` — lines=304; symbols=CorrelationManager, RiskManager, SmartRiskSizer
- `engine/risk_profiles.py` — lines=250; symbols=RiskProfile, calculate_position_size, filter_signal_by_profile, format_current_profile, format_profile_options, get_risk_profile, get_use...
- `engine/risk_sizer.py` — lines=205; symbols=SmartRiskSizer, calculate_position_size, get_risk_sizer
- `engine/scoring.py` — lines=449; symbols=calculate_confluence, calculate_signal_score, historical_winrate_score, htf_alignment_score, liquidity_pool_score, liquidity_score, ml_pr...
- `engine/shadow_outcome_worker.py` — lines=166; symbols=ShadowOutcomeWorker
- `engine/signal.py` — lines=18; symbols=Signal
- `engine/signal_analytics.py` — lines=99; symbols=SignalAnalytics, calculate_volume_delta
- `engine/signal_calculations.py` — lines=278; symbols=calculate_expected_loss, calculate_expected_profit, calculate_pips, calculate_position_size, calculate_profit_loss_pct, calculate_risk_re...
- `engine/signal_context.py` — lines=342; symbols=OneBiasPerTimeframe, SignalContext, SignalCooldownManager
- `engine/signal_controller.py` — lines=642; symbols=ControllerDecision, SignalController
- `engine/signal_dedup_strict.py` — lines=275; symbols=StrictSignalDedup, dedupe_signals_batch_strict, is_signal_duplicate_strict
- `engine/signal_deduplicator.py` — lines=1243; symbols=MLRejectionTracker, SignalDeduplicator, check_user_asset_cooldown, compute_cross_timeframe_fingerprint, compute_cross_timeframe_hash_key,...
- `engine/signal_explainability.py` — lines=210; symbols=build_signal_explanation
- `engine/signal_lifecycle.py` — lines=512; symbols=dispatch_event_notifications, dispatch_pending_event_notifications, entry_was_touched, evaluate_observation, event_state, record_lifecycl...
- `engine/signal_lock.py` — lines=317; symbols=SignalLock, acquire_signal_lock, active_signal_exists_for_asset, get_lock_ttl, is_signal_locked, release_signal_lock
- `engine/signal_metrics.py` — lines=158; symbols=resolve_confidence_ratio, resolve_confluence_percent, resolve_confluence_total, resolve_ml_probability, resolve_score_percent
- `engine/signal_monitor.py` — lines=247; symbols=SignalMonitor, start_signal_monitor, stop_signal_monitor
- `engine/signal_validator.py` — lines=202; symbols=create_signal_correction, notify_signal_correction, validate_signal
- `engine/signal_validators.py` — lines=274; symbols=normalize_signal_for_ml, normalize_tp_structure, validate_signal_structure
- `engine/similarity.py` — lines=469; symbols=SimilarityEngine, calculate_similarity_score, check_historical_similarity, check_historical_similarity_sync, get_historical_winrate, get_...
- `engine/smart_dca.py` — lines=430; symbols=DCAProfile, SmartDCA, get_user_dca_profile, monitor_dca_once, monitor_dca_opportunities, set_user_dca_profile
- `engine/stale_signal_validator.py` — lines=549; symbols=StaleSignalValidator, calculate_entry_zone, get_dynamic_threshold, get_threshold_from_env, get_validator, is_in_entry_zone, is_price_sane...
- `engine/stats_manager.py` — lines=122; symbols=GlobalStats
- `engine/strategies/__init__.py` — lines=4; symbols=none
- `engine/strategies/base.py` — lines=16; symbols=Strategy
- `engine/strategies/commodity.py` — lines=47; symbols=CommodityStrategy
- `engine/strategies/runner.py` — lines=93; symbols=run_strategy_with_marketstate, run_strategy_with_marketstate_async
- `engine/strategies/signal_generator.py` — lines=897; symbols=SignalGenerator, StrategySelector, StrategySignal
- `engine/strategy_orchestrator.py` — lines=358; symbols=StrategyOrchestrator, StrategyWeights, get_best_strategy, get_current_session, get_strategy_orchestrator, get_strategy_weights
- `engine/strategy_selector.py` — lines=19; symbols=get_best_strategies_for_asset
- `engine/threshold_optimizer.py` — lines=513; symbols=AdaptiveThresholdOptimizer, ThresholdConfig, get_current_threshold, get_threshold_optimizer, refresh_thresholds
- `engine/tier_notifications.py` — lines=436; symbols=TierNotificationManager
- `engine/tiered_executor.py` — lines=439; symbols=calculate_lot_size_premium, calculate_lot_size_vip, can_execute, can_execute_premium, can_execute_vip, execute_for_user, execute_premium_...
- `engine/timeframe_policy.py` — lines=216; symbols=TimeframeRequirement, TradingStyle, resolve_required_timeframes, validate_timeframe_requirement
- `engine/trade_manager.py` — lines=321; symbols=TradeManager, check_and_move_sl
- `engine/ultra_quality_filter.py` — lines=363; symbols=UltraQualityFilter
- `engine/webhook_generator.py` — lines=384; symbols=broadcast_outcome_webhook, broadcast_signal_webhook, build_cornix_payload, build_native_payload, build_outcome_payload, build_pinescript_...
- `engine/wfo.py` — lines=486; symbols=WalkForwardOptimizer
- `execution/__init__.py` — lines=15; symbols=none
- `execution/service.py` — lines=264; symbols=ExecutionGate, ExecutionRequest, ExecutionResult, GateDecision
- `find_debug_msg.py` — lines=28; symbols=none
- `find_dropna.py` — lines=32; symbols=none
- `find_dropna2.py` — lines=25; symbols=none
- `find_dropna_unsafe.py` — lines=24; symbols=none
- `find_ms.py` — lines=26; symbols=none
- `find_nofilter.py` — lines=24; symbols=none
- `find_pd_conv.py` — lines=31; symbols=none
- `find_skip_logging.py` — lines=12; symbols=none
- `find_yahoo_usage.py` — lines=25; symbols=none
- `fix2.py` — lines=23; symbols=none
- `fix3.py` — lines=82; symbols=none
- `fix_bot_resend.py` — lines=42; symbols=none
- `fix_commands.py` — lines=59; symbols=none
- `fix_created_at.py` — lines=57; symbols=check_and_add_column
- `fix_ml_column.py` — lines=46; symbols=add_ml_probability_column
- `fix_ml_drift.py` — lines=111; symbols=check_shadow_predictions, fix_ml_threshold, get_clean_asset_list, main
- `fix_require_tier.py` — lines=51; symbols=none
- `fix_require_tier2.py` — lines=37; symbols=none
- `fix_threshold.py` — lines=19; symbols=none
- `legacy_telegram/__init__.py` — lines=6; symbols=none
- `legacy_telegram/access.py` — lines=1; symbols=none
- `legacy_telegram/bot.py` — lines=40; symbols=main
- `legacy_telegram/commands.py` — lines=84; symbols=help_cmd, history, pricing, public_commands, start, stats, upgrade
- `legacy_telegram/formatter.py` — lines=16; symbols=format_signal
- `main.py` — lines=119; symbols=main
- `market/session_classifier.py` — lines=244; symbols=MarketSession, SessionState, get_asset_class_threshold, get_current_session, get_session_bonus, get_session_state, get_time_based_feature...
- `ml/__init__.py` — lines=26; symbols=none
- `ml/drift_monitor.py` — lines=61; symbols=detect_feature_drift, psi
- `ml/dynamic_threshold.py` — lines=374; symbols=adjust_threshold, calculate_dynamic_threshold, get_current_model_auc, get_dynamic_ml_threshold, get_prev_threshold, get_threshold_for_ass...
- `ml/evidence.py` — lines=268; symbols=EvidenceManifest, PerformanceMetrics, PromotionDecision, build_manifest, compute_metrics, evaluate_promotion, purged_walk_forward_splits,...
- `ml/features.py` — lines=180; symbols=extract_features, regime_to_int, strategy_to_int, timeframe_to_int
- `ml/feedback_loop.py` — lines=233; symbols=MLFeedbackLoop, get_ml_feedback_loop
- `ml/gen_model.py` — lines=54; symbols=none
- `ml/inference.py` — lines=253; symbols=MLFilter, calculate_dynamic_threshold, get_current_model_auc
- `ml/model_registry.py` — lines=171; symbols=ModelEntry, ModelRegistry, compute_model_hash_from_b64, extract_metadata, load_model_with_metadata, load_payload, load_registry, save_mod...
- `ml/optuna_tuner.py` — lines=31; symbols=tune_xgboost_params
- `ml/retrain.py` — lines=267; symbols=collect_training_data, retrain_model
- `ml/schema_version.py` — lines=82; symbols=get_current_schema_version, get_feature_columns, migrate_feature_payload, normalize_feature_columns, normalize_model_payload
- `ml/scorer.py` — lines=41; symbols=score_signal
- `ml/signal_calibrator.py` — lines=376; symbols=AssetClassPerformance, SignalCalibrator, calibrate_signal, record_signal_outcome
- `ml/train_model.py` — lines=1075; symbols=engineer_features, load_training_data, load_training_data_sync, main, save_model, train_model
- `parse_diagnostics.py` — lines=96; symbols=parse_heatmap_log
- `payments/invoice_service.py` — lines=372; symbols=InvoiceService, InvoiceStatus, generate_invoice, get_invoice, get_user_invoices
- `payments/models.py` — lines=23; symbols=Subscription
- `payments/payout_readiness.py` — lines=67; symbols=PayoutAccount, PayoutRequest, PayoutStatus, approve_payout, create_payout_request, payout_readiness_status
- `payments/paystack.py` — lines=311; symbols=handle_webhook, process_charge_success, process_event, process_subscription_create, process_subscription_disable, verify_payment, verify_...
- `payments/paystack_webhook.py` — lines=231; symbols=paystack_webhook
- `payments/receipt_service.py` — lines=126; symbols=PaymentReceipt, ReceiptService
- `payments/subscriptions.py` — lines=16; symbols=none
- `paystack/paystack.py` — lines=212; symbols=generate_paystack_link, match_amount_to_tier, verify_payment, verify_webhook_signature
- `railway_main.py` — lines=2554; symbols=lifespan, tradingview_webhook, tradingview_webhook_status
- `read_all_adapters.py` — lines=30; symbols=none
- `read_bot_nofilter.py` — lines=14; symbols=none
- `read_confluence.py` — lines=14; symbols=none
- `read_indicators.py` — lines=14; symbols=none
- `read_line.py` — lines=13; symbols=none
- `read_mtf.py` — lines=17; symbols=none
- `read_providers.py` — lines=14; symbols=none
- `read_risk.py` — lines=14; symbols=none
- `read_tracker.py` — lines=17; symbols=none
- `read_tv.py` — lines=27; symbols=none
- `read_yfin_current.py` — lines=14; symbols=none
- `read_yfin_full.py` — lines=14; symbols=none
- `read_yfinance_adapter.py` — lines=15; symbols=none
- `run_diag.py` — lines=140; symbols=run_full_diagnostic
- `run_ml_shadow_diagnostic.py` — lines=178; symbols=main, run_diagnostic
- `run_server.py` — lines=20; symbols=none
- `runtime/__init__.py` — lines=11; symbols=none
- `runtime/all_dev.py` — lines=25; symbols=run
- `runtime/analytics.py` — lines=59; symbols=run, run_async
- `runtime/bot.py` — lines=14; symbols=run
- `runtime/delivery.py` — lines=24; symbols=run, run_async
- `runtime/dispatcher.py` — lines=50; symbols=dispatch
- `runtime/engine.py` — lines=15; symbols=run
- `runtime/health.py` — lines=47; symbols=HealthCheck, HealthReport, livez, readyz, role_readiness
- `runtime/outcome.py` — lines=19; symbols=run, run_async
- `runtime/roles.py` — lines=216; symbols=RoleSpec, RunMode, SchedulerOwner, SchedulerOwnership, infer_run_mode, parse_run_mode, role_spec, scheduler_ownership
- `runtime/scheduler.py` — lines=284; symbols=PostgresAdvisorySchedulerLease, SchedulerLease, SchedulerLike, SchedulerOwnershipError, run, run_async
- `runtime/web.py` — lines=32; symbols=create_app, run
- `search_dropna.py` — lines=20; symbols=none
- `search_msg.py` — lines=20; symbols=none
- `search_nofilter.py` — lines=52; symbols=none
- `services/__init__.py` — lines=1; symbols=none
- `services/ai_review_router.py` — lines=60; symbols=AIReviewRouter, ReviewResult
- `services/asset_mapper.py` — lines=423; symbols=InstrumentSpec, canonicalize_symbol, classify_asset, get_all_providers_for_asset, get_instrument_spec, map_symbol
- `services/asset_position_manager.py` — lines=185; symbols=AssetPositionState, get_user_asset_position_state
- `services/asset_registry.py` — lines=211; symbols=AssetProfile, build_asset_profile, classify_asset, discover_asset_universe, filter_profiles, normalize_symbol
- `services/asset_repeat_policy.py` — lines=70; symbols=canonical_delivery_cooldown_key, get_asset_repeat_lock_hours, legacy_delivery_cooldown_keys
- `services/automated_analyst.py` — lines=44; symbols=run_automated_audit
- `services/broadcaster.py` — lines=424; symbols=BroadcasterService, get_broadcaster, run_broadcaster_service, start_broadcaster, stop_broadcaster
- `services/codex_governance.py` — lines=440; symbols=build_local_codex_recommendations, collect_codex_governance_context, get_last_codex_governance_review, run_codex_governance_review, run_e...
- `services/dead_letter_queue.py` — lines=353; symbols=DeadLetterQueue, get_dead_letter_queue
- `services/decision_intelligence.py` — lines=186; symbols=build_decision_record, persist_decision_record, validate_decision_record
- `services/dynamic_sizing.py` — lines=297; symbols=DynamicSizer, calculate_position_size, get_dynamic_sizer
- `services/economic_calendar.py` — lines=470; symbols=fetch_economic_events, get_macro_news_context, get_upcoming_events_summary, get_volatility_buffer_info, is_no_trade_zone, is_no_trade_zon...
- `services/ecosystem_policy.py` — lines=111; symbols=ConsentRecord, CopyTradeDecision, PaperFill, copy_trade_decision, deterministic_paper_fill, portfolio_snapshot
- `services/gemini_ml.py` — lines=899; symbols=analyze_market_regime, ask_gemini_custom_question, ask_gemini_signal_explanation, audit_recent, gemini_available, gemini_confluence_check...
- `services/market_intelligence.py` — lines=186; symbols=MarketIntelligence, detect_session, evaluate_market, market_to_signal_fields
- `services/mission_control.py` — lines=140; symbols=MissionSnapshot, build_mission_snapshot, format_mission, parse_tp_levels
- `services/mt5_bridge.py` — lines=558; symbols=MT5AccountManager, MT5Bridge, MT5Config, MT5Order, MT5Position, execute_signal, get_positions
- `services/mt5_client.py` — lines=1008; symbols=close_all_positions, close_position, ensure_user_mt5_account_id, execute_trade, get_account_info, get_live_price, get_live_quote, get_ope...
- `services/mt5_signal_router.py` — lines=1432; symbols=ExecutionMode, ExecutionRequest, ExecutionResult, MT5SignalRouter, get_user_execution_mode, route_signal_to_mt5, set_user_execution_mode
- `services/mt5_types.py` — lines=143; symbols=AccountInfo, MT5Constants, MetaTrader5, Order, Position, SymbolInfo, TradeResult
- `services/mtf_consensus.py` — lines=171; symbols=MultiTimeframeConsensus, TimeframeBias, analyze_mtf_consensus, infer_timeframe_bias, mtf_to_signal_fields
- `services/news_intelligence.py` — lines=202; symbols=affected_assets, assess_news, classify_event, deduplicate_stories, fake_news_risk, normalize_story, sentiment_score
- `services/opportunity_engine.py` — lines=105; symbols=OpportunityScore, rank_opportunities, score_opportunity
- `services/prompt_registry.py` — lines=65; symbols=prompt_file_path, prompt_version, render_prompt
- `services/provider_registry.py` — lines=302; symbols=ProviderHealth, ProviderRegistry, get_provider_for_asset, get_provider_registry, report_provider_failure, report_provider_success
- `services/security.py` — lines=85; symbols=decrypt_secret, encrypt_secret, is_encryption_available
- `services/signal_orchestrator.py` — lines=350; symbols=SignalOrchestrator, get_signal_orchestrator, is_significant_update
- `services/subscription_manager.py` — lines=505; symbols=SubscriptionManager, SubscriptionState, create_user_subscription, extend_user_subscription, get_subscription_status
- `services/tier_policy.py` — lines=73; symbols=TierCapabilities, apply_tier_visibility, get_tier_capabilities, tier_allows_signal
- `services/trade_profiles.py` — lines=291; symbols=TradeProfile, apply_trade_profile_to_signal, estimate_time_to_target, format_trade_profile_options, get_trade_profile, get_user_trade_pro...
- `services/trading_intelligence.py` — lines=80; symbols=enrich_signal_intelligence
- `services/trading_ledger.py` — lines=96; symbols=assert_valid_transition, normalize_position_state, record_signal_generated_event, record_trading_event
- `services/trading_mode_manager.py` — lines=534; symbols=TradingModeManager, execute_user_signal, get_trading_mode_manager, get_user_portfolio, get_user_trading_mode, switch_user_mode
- `services/upgrade_intents.py` — lines=89; symbols=build_upgrade_intent_event, record_upgrade_intent, schedule_upgrade_intent
- `services/user_intelligence.py` — lines=191; symbols=UserTradingPreferences, format_preferences, get_user_trading_preferences, normalize_risk_profile, preferences_from_payload, preferences_t...
- `services/waitlist_jobs.py` — lines=152; symbols=check_waitlist_capacity_job, monitor_expired_invites_job
- `signalrank_discord/__init__.py` — lines=1; symbols=none
- `signalrank_discord/webhook_dispatcher.py` — lines=17; symbols=dispatch_signal_webhook
- `signalrank_telegram/__init__.py` — lines=2; symbols=none
- `signalrank_telegram/access.py` — lines=106; symbols=resolve_user_tier
- `signalrank_telegram/account_commands.py` — lines=227; symbols=apikey_command, history_command, performance_command
- `signalrank_telegram/admin_commands.py` — lines=392; symbols=admin_dashboard, admin_top_assets_command, admin_top_strategies_command, admin_user_engagement_command, force_market_scan_command, selfch...
- `signalrank_telegram/bot.py` — lines=8426; symbols=auto_delete_old_signals_job, dispatch_signals, dispatch_signals_async, distribute_random_signals_to_free_users_job, downgrade_expired_sub...
- `signalrank_telegram/callback_handlers.py` — lines=514; symbols=callback_router, create_global_callback_handler
- `signalrank_telegram/command_access.py` — lines=605; symbols=check_command_access, get_accessible_commands, get_help_message, sync_command_help, tier_rank
- `signalrank_telegram/command_resilience.py` — lines=141; symbols=CachedCommandResponse, CommandResponseCache, acknowledge_command, schedule_background_task
- `signalrank_telegram/commands.py` — lines=8242; symbols=about_command, account_command, admin_broadcast_command, admin_command, admin_dashboard, admin_top_assets_command, admin_top_strategies_c...
- `signalrank_telegram/delivery_cooldown.py` — lines=281; symbols=check_active_signal_exists, check_delivery_cooldown, check_signal_lock, clear_delivery_cooldown, clear_signal_lock, set_delivery_cooldown...
- `signalrank_telegram/extended_commands.py` — lines=124; symbols=automaton_pause_command, automaton_report_command, automaton_reset_paper_command, automaton_resume_command, automaton_status_command, cod...
- `signalrank_telegram/feedback.py` — lines=78; symbols=FeedbackStore
- `signalrank_telegram/formatter.py` — lines=1409; symbols=format_performance_summary_vip, format_signal, format_signal_admin, format_signal_fallback_card, format_signal_free, format_signal_free_l...
- `signalrank_telegram/free_signal_jobs.py` — lines=64; symbols=distribute_random_signals_to_free_users_job, free_distribution_job
- `signalrank_telegram/httpx_config.py` — lines=7; symbols=none
- `signalrank_telegram/message_style.py` — lines=59; symbols=clean_message_text
- `signalrank_telegram/mt5_commands.py` — lines=128; symbols=mt5_link_command, mt5_status_command
- `signalrank_telegram/owner_commands.py` — lines=1237; symbols=add_vip_command, broadcast_command, correct_signal, dev_force_signal, dev_invalidate, dev_pause, dev_resume, owner_revenue, owner_users, ...
- `signalrank_telegram/payment_handler.py` — lines=148; symbols=check_pending_payments, format_tier_upgrade_confirmation, verify_payment_and_upgrade_tier
- `signalrank_telegram/rate_limit.py` — lines=18; symbols=rate_limited
- `signalrank_telegram/rich_messages.py` — lines=149; symbols=build_signal_rich_html, rich_messages_enabled, send_rich_message_raw
- `signalrank_telegram/signal_charts.py` — lines=250; symbols=build_signal_chart, render_signal_chart
- `signalrank_telegram/signal_commands.py` — lines=419; symbols=proof_command, signals_command
- `signalrank_telegram/signal_distribution.py` — lines=301; symbols=SignalDistributor, create_distributor
- `signalrank_telegram/tier_delivery.py` — lines=399; symbols=TierDeliveryManager, check_and_enforce_daily_limit, get_delivery_manager, get_paywall_upsell_message
- `signalrank_telegram/tier_gated_formatter.py` — lines=266; symbols=demo_format, format_tiered_signal, get_paywall_upsell_message, should_user_receive_signal
- `signalrank_telegram/tier_signal_formatter.py` — lines=928; symbols=format_premium_signal, format_premium_tp_update, format_vip_no_trade_alert, format_vip_signal, format_vip_tp_update
- `signalrank_telegram/timezones.py` — lines=147; symbols=age_seconds, as_utc, effective_user_timezone, format_user_datetime, format_user_time, resolve_timezone_query, should_store_location_coord...
- `signalrank_telegram/user_commands.py` — lines=152; symbols=about_command, account_command, disclaimer_command, faq_command, myid_command, start_command, status_command, support_command
- `signalrank_telegram/user_prefs.py` — lines=31; symbols=UserPrefsStore
- `signalrank_telegram/utils.py` — lines=272; symbols=require_tier, sanitize_input, tier_rank, validate_lot_size, validate_risk_pct
- `storage/db.py` — lines=1; symbols=none
- `strategies/__init__.py` — lines=195; symbols=run_all_strategies
- `strategies/base.py` — lines=24; symbols=BaseStrategy
- `strategies/commodity.py` — lines=11; symbols=best_commodity_strategies
- `strategies/crypto.py` — lines=11; symbols=best_crypto_strategies
- `strategies/dynamic_targets.py` — lines=148; symbols=DynamicTargets, calculate_dynamic_targets, enhance_signal_targets, get_tp_ladders_for_tier
- `strategies/fallback.py` — lines=452; symbols=SimplePriceActionStrategy, SimpleRangeBreakStrategy, SimpleTrendContinuationStrategy, SimpleVolumeConfirmationStrategy, UltraEmergencyStr...
- `strategies/fibonacci_confluence.py` — lines=304; symbols=fibonacci_confluence_strategies
- `strategies/fibonacci_helpers.py` — lines=24; symbols=is_price_in_golden_pocket
- `strategies/fx.py` — lines=11; symbols=best_fx_strategies
- `strategies/imp.py` — lines=433; symbols=institutional_momentum_pulse_strategies
- `strategies/liquidity_sweep.py` — lines=279; symbols=detect_liquidity_sweep_fvg, liquidity_sweep_strategies
- `strategies/momentum.py` — lines=272; symbols=MACDMomentumStrategy, RSIMomentumStrategy, StochRSIMomentumStrategy, momentum_strategies
- `strategies/stock.py` — lines=54; symbols=best_stock_strategies, stock_strategies, stock_trend_strategy
- `strategies/structure.py` — lines=130; symbols=LiquiditySweepStrategy, SRBreakRetestStrategy, StructureBiasStrategy, structure_strategy, structure_strategy
- `strategies/tradingview.py` — lines=397; symbols=get_tradingview_signals, tradingview_strategies
- `strategies/trend.py` — lines=209; symbols=ADXTrendStrategy, EMATrendStrategy, SupertrendStrategy, trend_strategies
- `strategies/volatility.py` — lines=95; symbols=ATRBreakoutStrategy, BBWidthVolatilityStrategy, KeltnerVolatilityStrategy, volatility_strategies
- `strategy_live_smoke.py` — lines=40; symbols=main
- `test_all_features.py` — lines=225; symbols=none
- `test_all_functions.py` — lines=121; symbols=TestAllFunctions
- `test_asset_routing.py` — lines=210; symbols=main, test_asset_type_detection, test_market_hours, test_provider_routing, test_strict_provider, test_ticker_namespacing
- `test_batch_engine.py` — lines=342; symbols=batch_fetch_market_data, test_batch_pipeline
- `test_batch_v2.py` — lines=84; symbols=test_batch
- `test_cache.py` — lines=39; symbols=none
- `test_commands_quick.py` — lines=29; symbols=collect_command_functions, test_commands_module_imports_and_compiles
- `test_core.py` — lines=48; symbols=TestSignalController, TestUserTier
- `test_data_fetch.py` — lines=37; symbols=test_live_data_fetch_and_indicators
- `test_dedup_import.py` — lines=18; symbols=none
- `test_diag.py` — lines=34; symbols=none
- `test_engine_diag.py` — lines=67; symbols=none
- `test_exact_healthz.py` — lines=32; symbols=none
- `test_fast.py` — lines=23; symbols=none
- `test_final.py` — lines=26; symbols=none
- `test_freshness_manual.py` — lines=156; symbols=test_freshness_validation
- `test_health_http.py` — lines=30; symbols=none
- `test_import_check.py` — lines=41; symbols=run_import_check, test_critical_imports
- `test_imports.py` — lines=53; symbols=none
- `test_market_data_manual.py` — lines=129; symbols=test_all_providers, test_binance_direct, test_single
- `test_mount_debug.py` — lines=32; symbols=none
- `test_mounted.py` — lines=38; symbols=none
- `test_near_zero_loss.py` — lines=362; symbols=test_position_sizing, test_smart_exits, test_trade_tracking, test_trailing_stop, test_ultra_quality_filter
- `test_news_feature.py` — lines=74; symbols=none
- `test_prod_sim.py` — lines=71; symbols=none
- `test_scoring_validation.py` — lines=126; symbols=test_component_scoring, test_ml_boost, test_quality_gates, test_regime_bonus, test_winning_signals
- `test_signal_chain.py` — lines=44; symbols=test_live_signal_chain_generates_or_explicitly_rejects
- `test_signal_gen.py` — lines=26; symbols=test_synthetic_signal_generation_smoke
- `test_signals_diag.py` — lines=50; symbols=test_signal_retrieval
- `test_startup.py` — lines=39; symbols=none
- `test_strategy_debug.py` — lines=83; symbols=test_signal_generation
- `test_tier_formatter.py` — lines=73; symbols=none
- `test_tier_gated.py` — lines=35; symbols=none
- `test_tradingview_integration.py` — lines=202; symbols=main, test_asset_examples, test_environment_variables, test_signals_no_limit, test_strategy_pipeline, test_tradingview_fx_crypto
- `test_uvicorn.py` — lines=24; symbols=none
- `test_zero_signals.py` — lines=149; symbols=test_fallback_strategies, test_indicators_calculation, test_run_all_strategies
- `tmp_find.py` — lines=11; symbols=none
- `tmp_search.py` — lines=16; symbols=none
- `tmp_search2.py` — lines=26; symbols=none
- `tmp_search_placeholders.py` — lines=26; symbols=none
- `tmp_test_market_state.py` — lines=9; symbols=none
- `utils/__init__.py` — lines=1; symbols=none
- `utils/async_runner.py` — lines=230; symbols=run_sync, submit_background_coro
- `utils/command_registry.py` — lines=585; symbols=CommandDefinition, generate_help_text, generate_menu_keyboard, get_command_definition, get_commands_for_tier, get_handler_for_command, is...
- `utils/httpx_client.py` — lines=54; symbols=close_client, get_client, retry_async
- `utils/logging_config.py` — lines=72; symbols=setup_logging
- `utils/market_hours.py` — lines=201; symbols=get_market_status, is_market_open, is_market_open_for_timeframe, resolve_broker
- `utils/proxy_manager.py` — lines=209; symbols=ccxt_proxy_config_sync, get_proxy, get_proxy_sync, next_proxy_url, next_proxy_url_sync, normalize_proxy_url, refresh_active_proxy_pool, r...
- `utils/symbol_normalizer.py` — lines=264; symbols=batch_normalize, get_base_asset, get_quote_asset, is_crypto, is_forex, normalize, normalize_pair
- `utils/timeutils.py` — lines=41; symbols=now_utc_naive, to_aware_utc, to_naive_utc
- `validate_adaptive_learning.py` — lines=285; symbols=main, validate_adaptive_learning_state, validate_db_schema, validate_decision_log_enrichment, validate_gemini_integration, validate_news_...
- `verify_system.py` — lines=207; symbols=SmokeResult, SystemVerifier, main
- `web/__init__.py` — lines=0; symbols=none
- `web/api.py` — lines=208; symbols=RevokeTokenRequest, RotateTokenRequest, authenticate_api_key, generate_api_key, get_current_token_meta, get_signals, get_user_by_apikey, ...
- `web/app.py` — lines=980; symbols=BrokerPermissionRequest, ExchangeBrokerLinkRequest, HealthResponse, MetricsResponse, SignalRequest, create_paystack_checkout, exchange_br...
- `web/userdash/app.py` — lines=63; symbols=dashboard, index, login, logout
- `worker/ai_feedback.py` — lines=340; symbols=PerformanceStats, apply_recommendation, gather_performance_stats, get_gemini_recommendation, main, run_ai_feedback
- `worker/asset_learning_worker.py` — lines=97; symbols=AssetLearningWorker
- `worker/market_monitor.py` — lines=227; symbols=MarketMonitor, start_market_monitor
- `worker/news_sync_worker.py` — lines=338; symbols=get_cached_high_impact_events, run_news_sync_job, start_news_sync_worker, sync_economic_events_to_db, sync_now
- `worker/proxy_worker.py` — lines=200; symbols=fetch_proxy_candidates, proxy_validation_enabled, proxy_validation_job, run_proxy_validation_cycle, validate_proxy
- `worker/worker.py` — lines=569; symbols=Worker, main

---

# 30. BINDING CROSS-CHAT DECISION LEDGER

# Cross-Chat Decision Ledger

Last updated: 2026-07-26

This file is the self-contained historical decision source for an implementation agent that cannot access prior conversations.

| Decision ID | Canonical decision | Supersedes/clarifies |
|---|---|---|
| SCD-001 | SignalRankAI is a Telegram-first full trading ecosystem, not just an alert bot. | Narrow signal-bot interpretations |
| SCD-002 | Initial Railway target is one coordinated async service, one Uvicorn worker, PostgreSQL and two Redis services. | Earlier multi-process suggestions |
| SCD-003 | PostgreSQL is durable truth; Redis is acceleration/queue state and must be reconstructible. | Redis-authoritative implementations |
| SCD-004 | Delivery proof requires successful Telegram response and persisted `sent_ok`, chat ID and message ID. | Generated/stored-as-delivered claims |
| SCD-005 | `/signals` defaults to active signals actually delivered to the requesting user in the last seven days. | Global/stored signal lists |
| SCD-006 | Canonical tiers are `free`, `premium`, `vip`, `admin`, `owner`. | Legacy aliases |
| SCD-007 | Canonical profiles are `scalp`, `day`, `swing`, `position`, `all`; day signals should normally resolve within one day. | Generic profile placeholders |
| SCD-008 | Product timeframes include 5m, 15m, 1h, 4h and 1d. | Provider-only timeframe assumptions |
| SCD-009 | Same-user same-asset repeat lock defaults to four hours after proven delivery, direction agnostic; active-position and fingerprint locks still apply. | Historical 12h/6h tier defaults |
| SCD-010 | Historical timeframe cooldown defaults: 15m 10m, 1h 20m, 4h 90m, 1d 6h, subject to latest central policy. | Inconsistent scattered defaults |
| SCD-011 | Prefer quality over forced signal frequency; a 60% win rate is an aspirational research target, never a guarantee or release assertion. | Frequency/win-rate pressure |
| SCD-012 | Generated, rejected, delivered, paper, shadow, backtest, walk-forward, demo and real execution performance remain separate. | Blended statistics |
| SCD-013 | Track rejected/near-miss candidates, MFE, MAE, duration, market context and technical features for offline ML. | Winner-only datasets |
| SCD-014 | Heavy training, SHAP and bulk replay do not run continuously on the live Railway monolith. | Live in-process training |
| SCD-015 | Multi-provider support must be capability-, quota-, freshness- and provenance-aware; public/mock tests do not equal live certification. | Provider-name-only integrations |
| SCD-016 | Supported markets include crypto spot/derivatives, FX, commodities, equities, indices and broker instruments where genuinely supported. | Crypto-only final product |
| SCD-017 | WebSockets are optional optimisations; REST must preserve correctness during degradation. | WebSocket-only correctness |
| SCD-018 | Every Telegram command and visible button is treated as unverified until end-to-end tested; callbacks ACK immediately and are idempotent. | Registration-only claims |
| SCD-019 | Early-exit warnings are recommendations and do not rewrite the official signal outcome. | Outcome manipulation |
| SCD-020 | Paystack public payments and real payouts remain disabled until test-mode reconciliation and support flows pass. | Premature paid release |
| SCD-021 | MetaApi/demo execution is the Railway-compatible broker path; native Windows MT5 cannot be pretended to run inside Railway Linux. | Unsafe native bridge assumptions |
| SCD-022 | Real execution, copy trading and Smart DCA remain gated by consent, account/spec/risk truth, idempotency, kill switch and separate approval. | Feature-presence-as-release |
| SCD-023 | The system must recover safely from DB pressure, Redis loss, provider outage, process restart and uncertain Telegram sends. | Happy-path readiness |
| SCD-024 | The implementation agent must keep working on unblocked tasks, request permissions in one queue and defend completion with reproducible evidence. | Plan-only/premature completion |

## Historical incidents that remain regression contracts

Database pool exhaustion; broadcasts failing; generated signals not received; callbacks not responding; provider outages; yfinance timestamp issues; CoinGecko instability; WebSocket restart loops; stored-only exposure contamination; Redis-empty mass expiry; synthetic ML contamination; TradingView route interception; waitlist import failures; Bybit category errors; derivative-as-spot errors; unsafe MT5 fallback sizing; Smart DCA state/account/Redis defects; fan-out N+1 queries; queue expiry; local `telegram` package shadowing; inconsistent UTC timestamps; and weakened token-rotation tests.


---

# 31. BINDING UNIVERSAL REQUIREMENT REGISTER

# Universal Requirement Register

Last updated: 2026-07-26
Status vocabulary: `IMPLEMENTED`, `VERIFIED_LOCAL`, `LIVE_PROOF_REQUIRED`, `BLOCKED_EXTERNAL`, `DISABLED_BY_POLICY`, `REVIEW_REQUIRED`.

This register reconciles the repository, the supplied v5 completion prompt, historical project documentation, previous Railway incidents, migrations, tests and deployment profiles. A passing unit test does not by itself change a live-proof requirement to complete.

| ID | Requirement | Implementation/evidence location | Current status | Remaining acceptance evidence |
|---|---|---|---|---|
| SR-RUN-001 | One canonical FastAPI Railway monolith, one process and one Uvicorn worker | `railway_main.py`, `web/app.py`, `start.sh`, Railway env profiles | VERIFIED_LOCAL | Railway staging boot and soak |
| SR-DB-001 | PostgreSQL durable truth and PgBouncer-safe bounded sessions | `db/session.py`, `db/priority.py`, migrations, DB audits | VERIFIED_LOCAL | Real PgBouncer transaction-pool test |
| SR-REDIS-001 | Separate state and delivery Redis roles with bounded pools | `core/redis_state.py`, `core/redis_streams.py`, env profiles | VERIFIED_LOCAL | Live two-Redis outage/recovery test |
| SR-REDIS-002 | Redis loss must rebuild from PostgreSQL, never erase durable signals | recovery services and regression tests | VERIFIED_LOCAL | Staging flush/restart evidence |
| SR-SIG-001 | Generated/stored/delivered/paper/shadow/backtest/demo/live evidence stays separate | models, repositories, performance and outcome services | VERIFIED_LOCAL | Same-signal live lifecycle evidence |
| SR-DEL-001 | Telegram success plus `sent_ok`, chat/message IDs and active message constitute delivery proof | delivery pipeline and `SignalDelivery` | VERIFIED_LOCAL | Dedicated Telegram test-bot proof |
| SR-DEL-002 | Same-user same-asset repeat lock defaults to four hours after proven delivery | `services/asset_repeat_policy.py`, `db/pg_features.py`, bot/dedup paths | VERIFIED_LOCAL | Staging restart and Redis-loss proof |
| SR-DEL-003 | Delivery fan-out is batched, bounded, idempotent and RetryAfter-aware | broadcaster/delivery paths and tests | VERIFIED_LOCAL | Network load and uncertain-send tests |
| SR-PROF-001 | `scalp`, `day`, `swing`, `position`, `all` persist and alter engine/delivery policy | trade profiles, preferences, Telegram profile flows | VERIFIED_LOCAL | Full profile × tier staging matrix |
| SR-TIER-001 | Canonical tiers `free`, `premium`, `vip`, `admin`, `owner` | tier constants, access policy and commands | VERIFIED_LOCAL | Payment/entitlement staging matrix |
| SR-ASSET-001 | Crypto, FX, commodities, equities, indices and correctly classified derivatives | asset mapper, registry, providers, strategies | VERIFIED_LOCAL | All enabled classes live data E2E |
| SR-PROV-001 | Every enabled provider has capability metadata, validation, rate controls and certification status | `data/provider_catalog.py`, connectors, `scripts/certify_providers.py` | VERIFIED_LOCAL | Public/sandbox/keyed live certification |
| SR-PROV-002 | Delayed/historical providers cannot silently become live execution truth | provider catalog/routing and validation | VERIFIED_LOCAL | Cross-provider live freshness evidence |
| SR-STRAT-001 | Registered strategies declare supported assets/timeframes and return valid geometry | strategy registry and tests | VERIFIED_LOCAL | All-strategy compatible-data orchestration |
| SR-RISK-001 | Advisory and execution risk gates are fail-closed when critical state is unavailable | engine, risk, exposure, broker gates | VERIFIED_LOCAL | Staging fault-injection evidence |
| SR-OUT-001 | TP/SL/missed/expiry lifecycle, MFE/MAE, R and notifications are idempotent | lifecycle/outcome services and tests | VERIFIED_LOCAL | Natural/replay same-signal staging proof |
| SR-ML-001 | Structured positive and rejected-candidate telemetry is collected without live heavy training | telemetry, rejection spool, model registry | VERIFIED_LOCAL | Production telemetry sample/export evidence |
| SR-ML-002 | Offline export/training is leakage-aware and promotion is governed | ML scripts/docs | REVIEW_REQUIRED | Complete offline pipeline evidence and model card |
| SR-TG-001 | Every registered command and visible callback is reachable, role-gated and prompt-ACKed | Telegram modules and command-contract tests | VERIFIED_LOCAL | Dedicated bot full command/button run |
| SR-TV-001 | TradingView alerts are authenticated, fresh, idempotent and pass normal risk/delivery gates | FastAPI route and tests | VERIFIED_LOCAL | Signed staging webhook test |
| SR-PAY-001 | Paystack verification, HMAC, idempotency, entitlement, receipt/refund/reconciliation | payment services and tests | VERIFIED_LOCAL | Paystack test-mode E2E |
| SR-BROKER-001 | MetaApi/MT5 demo path uses live quote/spec/account, no fake balance or fallback lot | broker abstraction, router, bridge and tests | VERIFIED_LOCAL | MetaApi demo E2E/reconciliation |
| SR-BROKER-002 | Real execution/copy trading requires independent approval and remains disabled | execution flags and gates | DISABLED_BY_POLICY | Separate security/risk pilot |
| SR-OBS-001 | Health/readiness, structured metrics, provider/DB/Redis/delivery diagnostics | web health and observability scripts | VERIFIED_LOCAL | Railway metrics/alerts/soak |
| SR-SEC-001 | Secrets, webhook auth, RBAC, replay, IDOR and log-redaction controls | security tests/configuration | VERIFIED_LOCAL | Staging penetration/dependency evidence |
| SR-TEST-001 | Complete local orchestrator runs static, env, schema, governance, Railway simulation, fan-out, provider and integration checks | `scripts/run_complete_system_test.py`, `artifacts/complete-system-test-final/` | VERIFIED_LOCAL | Live Railway and external integrations remain separate |
| SR-REL-001 | Clean-room deploy, Railway staging, owner proof and 24–72 hour soak precede public release | deployment/runbooks | LIVE_PROOF_REQUIRED | Owner permissions and credentials |

## Unresolved business decisions

- Exact current weekly/monthly subscription prices.
- Whether any tier-specific same-asset cooldown should explicitly override the canonical four-hour default.
- Final public daily signal/score policy where historical documents conflict with current constants.
- Data-retention periods requiring legal/business approval.
- Real-execution release scope and jurisdictions.


---

# 32. EXTERNAL BLOCKER AND PERMISSION REGISTER

# Permission And External Blocker Register

Last updated: 2026-07-26

Secrets must be added directly to sealed staging/Railway variables. They must not be pasted into reports or chat.

| ID | Classification | Required input/permission | Blocks | Work already completed | Owner action |
|---|---|---|---|---|---|
| BLK-001 | PRODUCTION_ACCESS_REQUIRED | Railway staging project and deploy permission | Staging/soak proof | Code, profiles and local verification tooling | Grant staging access or deploy supplied release |
| BLK-002 | SECRET_REQUIRED | Dedicated Telegram test-bot token, webhook secret and test chat IDs | Full command/callback/delivery proof | Hermetic Telegram contracts | Add sealed variables and test identities |
| BLK-003 | SECRET_REQUIRED | Staging PostgreSQL/PgBouncer URL | Real DB compatibility/recovery | Schema/session/migration tests | Provision Railway Postgres reference |
| BLK-004 | SECRET_REQUIRED | Separate RedisState and RedisDelivery URLs | Queue/outage/recovery proof | Redis contracts/stream tests | Provision two Railway Redis services |
| BLK-005 | PROVIDER_CREDENTIAL_REQUIRED | Keys for selected keyed providers | Keyed live certification | Adapters, fixtures and certification framework | Add only selected provider keys |
| BLK-006 | SECRET_REQUIRED | Gemini key and approved bounded budget | Live AI gateway proof | Circuit/fallback tests | Add optional sealed key |
| BLK-007 | OWNER_PERMISSION_REQUIRED | TradingView staging secret/test alert | Signed alert E2E | Route/contracts complete | Send a staging alert after secret set |
| BLK-008 | SECRET_REQUIRED | Paystack test keys and webhook | Payment/reconciliation proof | Payment tests complete | Add test-mode keys only |
| BLK-009 | BROKER_DEMO_ACCOUNT_REQUIRED | MetaApi token and demo account | Broker demo E2E | Broker fail-closed code/tests | Provide demo-only account permission |
| BLK-010 | OWNER_INFORMATION_REQUIRED | Current subscription prices/periods | Public payment activation | Product flows/config ready | Confirm canonical business policy |
| BLK-011 | LEGAL_OR_COMPLIANCE_DECISION_REQUIRED | Retention/privacy/support policy | Public release governance | Safe configurable retention foundation | Supply approved policy |
| BLK-012 | IRREVERSIBLE_ACTION_APPROVAL_REQUIRED | Approval before production migration, user broadcast, payment or real trade | Production changes | Safe deployment/rollback tooling | Explicit approval per action |


---

# 33. TECHNICAL-DEBT REGISTER TO RESOLVE OR MIGRATE

# Living Technical Debt Register

Date opened: 2026-06-29
Last updated: 2026-07-26
Owner: Engineering

This register tracks verified technical, architectural, code quality,
performance, security, UX, ML, AI prompt, testing, documentation,
infrastructure, and operational debt. No debt item should disappear silently.

## Schema

Each item must include: unique ID, title, description, affected subsystems,
root cause, severity, likelihood, impact, dependencies, proposed solution,
estimated implementation effort, regression risk, current status, verification
evidence, date opened, date resolved, and owner.

## Open And Accepted Items

| ID | Title | Description | Affected Subsystems | Root Cause | Severity | Likelihood | Impact | Dependencies | Proposed Solution | Effort | Regression Risk | Status | Verification Evidence | Date Opened | Date Resolved | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LTD-002 | External provider integration confidence | Provider-capable news, on-chain, Gemini, Telegram, broker, and market-data paths are mostly tested with deterministic fakes. | `data`, `services`, `engine`, `signalrank_telegram`, `payments` | CI safety and missing sandbox credentials | Medium | High | High: live production drift can escape unit tests | Provider sandbox credentials | Add opt-in live integration tests gated by env flags. | High | Low | Open | Full suite green, but live E2E is not enabled. | 2026-06-29 |  | Engineering |
| LTD-003 | Telegram E2E verification gap | Commands, callbacks, and formatters are covered by contracts, but every Telegram workflow is not exercised end-to-end. | `signalrank_telegram` | Bot API tests require sandbox token/chat | High | Medium | High: user-facing regressions | Telegram sandbox | Add `TELEGRAM_E2E_ENABLED=1` smoke suite and workflow checklist. | High | Medium | Open | `tests/test_command_contracts.py` exists; no full Bot API suite. | 2026-06-29 |  | Engineering |
| LTD-004 | Decision intelligence lifecycle integration | Structured decision records exist but are not yet wired into every signal lifecycle branch. | `engine/core.py`, `services/decision_intelligence.py`, `db` | New layer added after existing compact decision logging | Medium | High | Medium: weaker explainability coverage | Full-suite green checkpoint | Integrate `build_decision_record()` into issued, rejected, skipped, delayed, and suppressed branches. | Medium | Medium | Open | `services/decision_intelligence.py` and tests exist. | 2026-06-29 |  | Engineering |
| LTD-006 | Outcome tracker architecture split | State-machine helpers and polling/backfill tracker coexist. | `engine/realtime_outcome_tracker.py` | Compatibility merge preserved both approaches | Medium | Medium | Medium: duplicate mental model | Shadow comparison | Run shadow comparison and decide primary tracker architecture. | Medium | Medium | Open | Realtime tracker tests pass; architecture decision pending. | 2026-06-29 |  | Engineering |
| LTD-007 | Generated/runtime inventory boundary | `.venv`, `.git`, bytecode, and caches are excluded from source audit. | repository operations | Boundary between source audit and supply-chain review | Low | High | Low: documented scope issue | Lockfile/supply-chain tooling | Treat as accepted application boundary; run separate dependency review when required. | Low | Low | Accepted | Audit report documents exclusion. | 2026-06-29 |  | Engineering |
| LTD-008 | Enterprise observability maturity | Health endpoints and Prometheus metrics exist, but dashboards, alert ownership, and SLOs are not yet complete. | `core`, `engine`, `web`, `worker`, deployment | Operational layer grew after product logic | High | Medium | High: production incidents harder to detect | Metrics backend, alerting target | Add structured dashboards, alert thresholds, SLOs, and on-call runbooks. | High | Medium | Open | Verified `core/telemetry.py`, `/metrics/prometheus`, `/health`, `/healthz`, and telemetry tests. | 2026-06-29 |  | Engineering |
| LTD-009 | Premium UX full rewrite | Every user-facing message has not yet been comprehensively rewritten to a premium standard. | `signalrank_telegram`, `web`, `payments` | Large message surface area | Medium | High | Medium: conversion and trust impact | UX register inventory | Audit commands/messages one workflow at a time and add snapshot tests. | High | Medium | Open | UX register created with known gaps. | 2026-06-29 |  | Product/Engineering |

## Closed Items

| ID | Title | Resolution | Verification Evidence | Date Opened | Date Resolved | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| LTD-C01 | Same-path divergent symbol gaps | Closed with subsystem-safe compatibility review. | AST scan: `same_path_symbol_gap_files=0`, `ref_only=0`, `target_only=0` for owned Python files. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C02 | Telegram unknown command fallback | Added top-level `_handle_unknown_command` registered after concrete handlers. | Targeted command tests and full suite passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C03 | Dead signal action callbacks | Signal keyboards no longer emit a trade callback when no signal id exists. | `tests/test_command_contracts.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C04 | On-chain exchange-flow veto | `OnChainAlpha` now uses configured provider context for inflow/outflow vetoes. | `tests/test_onchain_providers.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C05 | TP dict parsing | Realtime outcome TP parsing accepts `price`, `tp`, `target`, and numeric entries. | `tests/test_time_stop_outcome_persistence.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |

| LTD-C06 | Time handling modernization | Runtime `datetime.utcnow()` calls were replaced by shared UTC helpers; source scan and full suite are clean. | `grep` source audit, compileall, and final full suite. | 2026-06-29 | 2026-07-26 | Engineering |

| LTD-C07 | Runtime configuration snapshot and drift validation | Added secret-safe runtime snapshots, canonical Railway profiles, duplicate-key validation, environment-contract tests, and pre-deploy orchestration. | `scripts/runtime_config_snapshot.py`, `scripts/validate_env_contract.py`, env tests and complete-system report. | 2026-06-29 | 2026-07-26 | Engineering |

## Maintenance Rule

Update this file after every audit, implementation, refactor, optimization, or
release-hardening pass. Closed items must retain resolution evidence.


---

# 34. LATEST PGBOUNCER AND TELEGRAM COMMAND RECOVERY LESSONS

# SignalRankAI PgBouncer and Telegram Command Recovery Report

Date: 2026-07-26

## Release status

`CODE_FIXED_AND_HERMETICALLY_VERIFIED__LIVE_RAILWAY_PROOF_PENDING`

This release fixes the runtime failure shown by Railway: an anonymous critical
DB session remained open while the outcome tracker and Telegram commands waited
for the only critical admission lane. It also hardens the full Telegram webhook
and command path for Railway PgBouncer transaction pooling.

## Proven root cause

`refresh_active_signal_keyboards_once()` opened a DB session and retained it
while it:

1. iterated up to 500 active Telegram messages;
2. made Telegram API network calls;
3. opened nested sessions through `_load_signal_payload()`;
4. opened nested sessions through `_load_signal_engagement_counts()`.

With a two-session application budget and one critical lane, that design could
self-deadlock and starve `outcome_tracker.fetch_active_signals`. Because the
session lacked a label, the old diagnostics displayed only `unlabelled`.

## Implemented fixes

### PgBouncer contract

- Auto-detects `pgbouncer` endpoints and supports explicit
  `DB_PGBOUNCER_MODE=1`.
- Uses SQLAlchemy `NullPool` behind PgBouncer rather than a second persistent
  application connection pool.
- Reuses one shared NullPool engine across event loops.
- Disables asyncpg statement cache and SQLAlchemy asyncpg prepared-statement
  cache.
- Generates unique prepared-statement names.
- Keeps application admission capped at two concurrent sessions.
- Disables runtime schema mutations and `create_all()` behind PgBouncer.
- Keeps Alembic in Railway pre-deploy as the only schema owner.
- Disables session-level scheduler advisory locks behind PgBouncer.

### DB admission and leak diagnosis

- Every session receives a real label derived from operation context and Python
  caller when no explicit label is supplied.
- Telegram commands and callbacks inherit `INTERACTIVE` DB priority.
- Active holders include caller, task, loop, thread and acquisition stack.
- Runtime watchdog reports sessions held over ten seconds and escalates those
  over thirty seconds.
- Session rollback/close is cancellation-safe.
- Admission tokens and semaphores release in guaranteed `finally` paths.
- Deployment diagnosis fails when anonymous or long-held sessions exist.

### Startup keyboard refresh deadlock

- Reads signal/message/outcome/engagement data in one bounded BACKGROUND DB
  transaction.
- Copies plain snapshots and closes the session before any Telegram API call.
- Removes recursive nested DB session calls.
- Uses bounded Telegram concurrency and per-call timeout.
- Is disabled by default on Railway.
- When explicitly enabled, runs as a delayed one-shot job after webhook
  readiness rather than blocking bot startup.

### Telegram webhook and commands

- Explicit `TELEGRAM_WEBHOOK_SECRET` remains preferred.
- A stable HMAC-derived fallback uses `API_TOKEN_PEPPER` and the bot token so
  `setWebhook` and the HTTP route cannot disagree.
- Deploys preserve pending Telegram updates by default.
- Redis ingress falls back to the bounded in-process queue.
- Every 503 path logs a structured rejection reason and queue diagnostics.
- Every command acknowledges quickly, runs with a bounded timeout and records a
  secret-safe runtime lifecycle.
- User-facing failures include a reference ID.
- Command audit writes are detached and ANALYTICS priority.
- `/diagnostics/commands` exposes the live handler graph, recent command runs,
  DB admission diagnostics and webhook queue state behind a sealed key.
- Safe live command probe submits selected read-only commands to a dedicated
  test chat and verifies receipt/completion through the runtime ledger.

### Complete command and callback audit

`scripts/audit_telegram_commands.py` inventories:

- 146 unique commands;
- 13 callback handler registrations;
- resilience-wrapper coverage;
- required core commands;
- duplicate/conditional registrations;
- commands safe for automatic live probing;
- commands requiring fixtures;
- commands requiring explicit permission because they can mutate credentials,
  payments, execution, users or system state.

Current audit classification:

- 16 safe automatic live probes;
- 107 commands requiring a fixture/manual semantic test;
- 23 permission-sensitive commands that must never be auto-executed blindly.

## Verification completed

Full repository test suite:

```text
748 passed
1 skipped
0 failed
```

The skipped test requires an optional dependency.

Complete local orchestrator:

```text
compileall                 PASS
environment contracts      PASS
schema audit               PASS
architecture smoke         PASS
DB session API audit       PASS
governance validation      PASS
secret scan                PASS
production readiness       PASS
runtime configuration      PASS
Railway simulation         PASS
100,000-user fan-out        PASS
provider certification     PASS
full pytest                 PASS
overall                     PASS
```

Additional results:

- 22 Alembic revisions.
- One migration head: `0022_active_guard_reconcile`.
- Zero legacy DB session API call sites.
- Zero secret-scan findings.
- 146 unique Telegram commands inventoried.
- 13 callback handlers inventoried.
- No missing required command.
- No unwrapped command registration.

The full suite was executed with compatible pure-Python Telegram/APScheduler
packages recovered from the user-provided project environment because the base
analysis container did not include those packages. The Railway build installs
its canonical versions from `requirements.txt` and still needs live proof.

## Automatic Railway diagnosis

Pre-deploy remains:

```bash
python -m alembic upgrade head && \
python scripts/deployment_diagnostics.py \
  --phase predeploy \
  --strict-core \
  --output /tmp/signalrank_predeploy_diagnostics.json
```

After startup, runtime diagnosis checks the HTTP service, schema, PgBouncer
contract, both Redis services, Telegram, queue state, DB holders, providers and
optional safe command probe. Missing credentials/tools are reported as
`BLOCKED`, not passed.

## Required first deployment state

Use the supplied PgBouncer recovery environment and retain:

```env
RUN_ENGINE_LOOP=0
RUN_WORKER_LOOP=1
WS_INGEST_ENABLED=0
CRYPTO_WS_ENABLED=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
PAYMENTS_PUBLIC_ENABLED=0
REAL_PAYOUTS_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
MT5_ALLOW_LIVE_ACCOUNTS=0
```

Set and seal a genuine `TELEGRAM_WEBHOOK_SECRET` and
`DEPLOYMENT_DIAGNOSTICS_KEY`.

## Live release gate

Do not enable the engine until the new Railway deployment proves for at least
one hour:

- no anonymous/unknown DB holder;
- no DB session held over ten seconds;
- no outcome tracker admission timeout;
- webhook HTTP 200 and pending updates return to zero;
- required live handler inventory passes;
- safe live command probe passes;
- REST market data remains usable;
- WebSocket workers remain disabled;
- no duplicate scheduler or Telegram delivery.

Then enable only owner-only crypto REST and prove one exact signal from
candidate through Telegram proof and terminal outcome. Public distribution,
payments, all assets and broker execution remain later independent gates.

## Evidence boundary

This release is not yet a claim of live production completion. Railway,
PostgreSQL through the user's PgBouncer, RedisState, RedisDelivery, Telegram
network delivery, natural signal lifecycle, payments, provider credentials and
broker demo execution require the next deployed evidence report and soak.


---

# 35. COMPLETE HISTORICAL V5 SPECIFICATION — BINDING REQUIREMENT REFERENCE

The following historical specification is included verbatim as a no-gap requirement source. Where it instructs modification of an existing repository, reinterpret it under the V6 clean-slate architecture. V6 sections and the latest owner decisions take precedence on conflict.


# SIGNALRANKAI — MASTER COMPLETION, PRODUCTION-HARDENING, MULTI-ASSET, ML-TELEMETRY, AND RAILWAY DEPLOYMENT PROMPT

## 0. YOUR ROLE

Act as the principal engineer, quantitative systems architect, senior Python/FastAPI developer, PostgreSQL/Redis specialist, Telegram platform engineer, DevSecOps engineer, SRE, QA lead, product engineer, broker-integration engineer, and production release manager for **SignalRankAI / SignalRankAI1**.

You are not being asked to give general advice, produce mockups, write pseudocode, or return a checklist without modifying the project. You must inspect the supplied repository, logs, master project document, previous audit reports, pasted implementation notes, migrations, tests, environment profiles, and deployment files; then directly complete, repair, integrate, test, document, and package the entire project.

Work for as long as required. Do not stop after identifying issues. Do not stop after writing a plan. Do not stop after fixing only errors visible in the logs. Continue until every verifiable acceptance criterion in this prompt has either passed or is explicitly documented as blocked by an external dependency that cannot be simulated locally, such as a missing third-party credential or a live broker approval.

Do not claim that the system is “perfect”, “100% safe”, “guaranteed profitable”, or “production ready” merely because unit tests pass. Production readiness must be proven with evidence. Never fabricate test results, provider availability, Telegram sends, market prices, broker responses, payment events, performance statistics, or win rates.

---

# 1. PRIMARY MISSION

Transform the supplied SignalRankAI repository into a complete, coherent, secure, low-latency, production-scale, multi-user, Telegram-first, multi-asset trading-intelligence ecosystem that:

1. Runs on **one Railway Hobby service** using one coordinated asynchronous Python process and one Uvicorn worker by default.
2. Uses:
   - PostgreSQL as the durable source of truth.
   - PgBouncer-compatible database access.
   - Redis instance 1 for shared state, cache, locks, provider health, market buffers, and recoverable runtime coordination.
   - Redis instance 2 for critical Telegram/webhook/delivery queues, delivery reservations, retries, and delivery-state coordination.
3. Supports:
   - Crypto spot.
   - Crypto perpetuals/futures/options where provider support exists.
   - Forex.
   - Commodities.
   - Stocks/equities.
   - Indices.
   - Derivatives.
   - Analysis-only macro/yields/volatility assets where appropriate.
4. Integrates free and low-cost data providers through a verified, quota-aware, capability-aware routing layer.
5. Supports Telegram commands, callbacks, profiles, subscriptions, payments, delivery, active-message updates, outcomes, paper trading, shadow tracking, reports, administration, MT5/MetaApi, TradingView alerts, and guarded copy/auto-execution.
6. Tracks every generated, rejected, delayed, suppressed, delivered, missed, expired, paper, shadow, backtest, and live-outcome event with correct provenance.
7. Collects complete machine-learning telemetry without running memory-heavy training jobs inside the live Railway monolith.
8. Reduces latency without starving PostgreSQL, flooding Telegram, violating provider quotas, duplicating work, or risking out-of-memory termination.
9. Recovers safely after Redis loss, provider outages, process restarts, deployment restarts, incomplete delivery attempts, and temporary database pressure.
10. Produces a fully updated codebase, migrations, tests, environment profiles, deployment instructions, release report, checksums, and a final evidence-backed readiness verdict.

---

# 2. INPUTS AND SOURCE-OF-TRUTH ORDER

You will be given some or all of the following:

- Current repository archive.
- Latest Railway logs.
- Master project document.
- Previous release reports and governance registers.
- Pasted implementation suggestions and code examples.
- Existing `.env` examples and Railway profiles.
- Existing migration chain.
- Existing tests.
- Previous patch archives.
- Current Git history, if included.

Use this source order when information conflicts:

1. Current repository code and migrations.
2. Latest production logs.
3. Latest dated audit/release report.
4. Master project document.
5. Earlier conversation requirements and governance registers.
6. Pasted example code.
7. General assumptions.

Pasted code is illustrative, not automatically correct. Adapt it to the actual repository structure, installed libraries, naming conventions, SQLAlchemy models, async Redis client, FastAPI application, Telegram library, and migration system. Do not create duplicate frameworks such as a second database package, second signal lifecycle, second Telegram router, second FastAPI app, or parallel model hierarchy when the project already has canonical implementations.

Before changing code:

- Extract the repository.
- Identify the true project root.
- Initialise or inspect Git.
- Record a clean baseline.
- Inventory all Python modules, tests, migrations, environment files, start commands, provider connectors, bot commands, callbacks, scheduler jobs, workers, models, and deployment files.
- Run static import/compile checks.
- Run the existing test suite in bounded groups if the whole suite exceeds the execution timeout.
- Search for TODO, FIXME, pass, NotImplementedError, placeholder credentials, hard-coded user IDs, fake balances, synthetic production data, unsafe defaults, silent exception swallowing, dead code, duplicate ownership, synchronous I/O in async functions, and unbounded queues/tasks.

Do not delete working functionality merely to simplify the project.

---

# 3. NON-NEGOTIABLE TRUTH AND SAFETY RULES

## 3.1 Signal truth

A generated candidate, high score, stored database row, Redis key, or attempted Telegram call is not proof of a delivered signal.

A live signal becomes valid delivery evidence only after all applicable stages are persisted:

1. Candidate generated.
2. Candidate passed deterministic eligibility and risk gates.
3. Signal stored.
4. User-specific delivery reservation acquired.
5. Telegram send attempted.
6. Telegram API returned success.
7. `sent_ok=true` persisted.
8. Telegram chat ID persisted.
9. Telegram message ID persisted.
10. Active-message record persisted.
11. Lifecycle entered `WATCHING_FOR_ENTRY`.
12. Entry touched or missed using valid market data.
13. Active state progressed correctly.
14. Terminal outcome persisted with provenance.
15. Outcome notification sent and proven.

Generated, rejected, stored, delivered, paper, shadow, backtest, walk-forward, demo-executed, and real-executed outcomes must remain separate evidence classes.

## 3.2 Financial safety

- No guaranteed profit, win rate, returns, or signal frequency.
- No hiding losses, missed entries, expiry, delivery failures, provider failures, slippage, fees, or latency.
- Never use stale data as fresh.
- Never use synthetic bootstrap data as live production evidence.
- Never infer an outcome from incomplete candles without an explicit and documented policy.
- Never execute real money without explicit user consent, eligible tier, linked account, validated credentials, risk configuration, live quote, symbol specification, idempotency key, kill-switch clearance, and reconciliation.
- Missing risk, quote, account, margin, lot-step, spread, market-session, or broker data must block real execution.
- Never fall back to `0.01` lots after a sizing error.
- Paper/demo execution may be active by default; real execution must be separately gated.

## 3.3 “Everything enabled” definition

“Everything enabled” means every feature is:

- Fully implemented.
- Registered and reachable.
- Covered by configuration.
- Tested.
- Observable.
- Recoverable.
- Safe under missing-provider and low-resource conditions.

It does not mean all heavy tasks run continuously at the same moment. The production monolith must use resource-aware scheduling and graceful degradation. Heavy ML training, large backtests, bulk exports, and historical replay must run on demand, locally, in CI, or in bounded maintenance windows—not continuously in the live process.

---

# 4. REQUIRED RUNTIME ARCHITECTURE

## 4.1 Railway Hobby topology

Default production topology:

- One Railway application service.
- One Python process.
- One Uvicorn worker.
- One FastAPI application: the canonical `railway_main:app` or the verified current equivalent.
- One coordinated asyncio event loop.
- Bounded background tasks with explicit ownership.
- PostgreSQL through PgBouncer.
- Two Redis instances.

Do not launch duplicate engine, bot, scheduler, outcome, payment, and analytics processes inside the same container unless the code has explicit role ownership preventing duplicate work and measured memory proves it is safe.

Use a single-process async modular monolith by default because separate Python processes duplicate:

- Python interpreter memory.
- pandas/NumPy imports.
- SQLAlchemy engines.
- Redis pools.
- HTTP clients.
- Telegram application state.
- strategy registry.
- scheduler state.
- ML/model imports.

Provide optional runtime roles for future scaling, but ensure the one-service profile is fully functional.

## 4.2 Explicit task ownership

Create a central ownership registry or runtime-role contract for:

- Gateway/webhook ingress.
- Telegram commands/callbacks.
- Signal engine.
- Delivery.
- Outcome tracking.
- Market monitor.
- WebSocket ingestion.
- Payments.
- Scheduler/maintenance.
- Shadow learning.
- ML inference.
- ML training.
- Drift monitoring.
- Asset learning.
- Waitlist jobs.
- Resend jobs.
- Free-user distribution.
- Reconciliation.
- State recovery.

No job may have two owners in the same deployment.

## 4.3 Resource governor

Implement or complete a resource governor that measures:

- Process RSS.
- Container/cgroup memory limit when available.
- CPU pressure where practical.
- Event-loop lag.
- DB admission queue pressure.
- Redis latency.
- delivery queue depth.
- provider error rate.
- Telegram RetryAfter rate.
- pending task count.

Expose states such as:

- `OPTIMAL`
- `CONSERVATIVE`
- `MINIMAL`
- `CRITICAL`

Use configurable thresholds and hysteresis. Do not hard-code a universal 512 MB ceiling.

At elevated pressure:

- Reduce provider concurrency.
- Reduce universe batch size.
- Disable optional timeframe fetching.
- Defer Gemini explanations.
- Defer asset discovery refresh.
- Defer ML inference if optional.
- Pause ML training, drift, shadow backfill, historical replay, bulk reports, and exports.
- Preserve health endpoints, webhook acknowledgements, Telegram commands, delivery proof, lifecycle tracking, kill switches, broker reconciliation, payment webhook verification, and database truth.

At critical pressure:

- Fail closed for new real-money execution.
- Stop opening new heavy scans temporarily.
- Continue tracking existing live positions and critical user interactions.
- Emit a structured alert.
- Recover automatically with hysteresis after pressure clears.

---

# 5. DATABASE, PGBOUNCER, AND MIGRATIONS

## 5.1 Database contract

PostgreSQL is the durable source of truth. Redis is never the only copy of:

- Signal lifecycle state.
- Delivery proof.
- Active messages.
- User entitlements.
- Broker orders.
- Payments.
- Outcomes.
- ML telemetry.
- Consent.
- Kill switches.
- Critical audit events.

Ensure PgBouncer transaction-pooling compatibility. Verify and correctly configure asyncpg statement/prepared-statement behaviour. Do not use session-level assumptions that transaction pooling breaks.

Use one canonical async engine/session API with:

- Priority.
- Label.
- Timeout.
- Admission control.
- Metrics.
- Cancellation safety.
- Rollback safety.

Keep:

- Small Railway pool.
- Zero overflow.
- Explicit short-lived sessions.
- No ORM sessions held across network calls.
- No database transaction held while calling Telegram, Gemini, market providers, Paystack, MetaApi, MT5, or TradingView processing.

## 5.2 Migration requirements

- Inspect every migration.
- Ensure one head.
- Create new rerunnable forward migration(s) for all schema changes.
- Do not edit old applied migrations unless the project’s migration policy explicitly permits it.
- Add indexes that match actual production queries.
- Avoid excessive indexes on write-heavy telemetry.
- Use timezone-aware timestamps consistently.
- Resolve naïve/aware datetime mismatches.
- Use `TIMESTAMPTZ` or a consistent UTC-naïve convention across model, migration, and query layers; do not mix them.
- Add check constraints/enums where helpful, but preserve compatibility.
- Include downgrade logic where feasible.
- Run schema audit and migration-head tests.

## 5.3 Database starvation prevention

Complete the non-blocking telemetry spool:

- Bounded in-memory queue or Redis-backed spool.
- Configurable max size.
- Batch size.
- Flush interval.
- Immediate flush at threshold.
- Retry with backoff.
- No loss on ordinary DB deferral.
- Spill to Redis when memory queue is full.
- Dead-letter handling.
- Metrics for queued, flushed, retried, dropped, oldest age, and batch latency.
- Short background-priority DB sessions.
- Bulk inserts.
- Graceful shutdown flush with timeout.
- No one-transaction-per-rejection pattern.

Batch-load user tier, preference, duplicate, quota, and entitlement data before fan-out. Avoid N+1 queries.

---

# 6. TWO-REDIS DESIGN

## 6.1 Redis 1: state/cache/market coordination

Use the primary Redis for:

- Provider health.
- Quote cache.
- OHLC cache.
- Market session cache.
- coalesced fetch locks.
- asset discovery cache.
- resource/degradation state.
- non-critical telemetry spool.
- market tick stream.
- active-trade acceleration cache.
- short-lived analytics caches.
- rate-limit counters.
- distributed task leases.

## 6.2 Redis 2: delivery/webhook-critical path

Use the delivery Redis for:

- Telegram webhook durable queue.
- user-update queue.
- delivery reservations.
- send retry queue.
- uncertain-send reconciliation.
- callback work queue.
- Telegram rate-limit state.
- active-message update queue.
- outcome notification queue.
- delivery dead-letter queue.

## 6.3 Redis stream correctness

Implement consumer groups rather than repeatedly reading from `0-0`.

Required semantics:

- `XADD` with configurable capped length.
- Consumer group creation.
- `XREADGROUP`.
- Acknowledge only after successful processing/persistence.
- Pending-entry recovery.
- Claim abandoned entries after lease timeout.
- Deduplication/idempotency keys.
- Dead-letter stream after maximum attempts.
- Stream lag and pending metrics.
- Backpressure.
- No `XDEL` before durable processing.
- Graceful consumer shutdown.

## 6.4 Redis loss recovery

On startup and when Redis is empty:

- Rebuild active signal/tracking caches from PostgreSQL.
- Rebuild delivery reconciliation state from undelivered/reserved/uncertain database rows.
- Rebuild active-message indexes.
- Rebuild outcome-tracking acceleration keys.
- Never mass-expire valid PostgreSQL signals merely because Redis is empty.
- Redis is a cache/queue accelerator, not the authority for historical truth.

---

# 7. MULTI-ASSET MARKET DATA PLATFORM

## 7.1 Canonical asset classes

Create or verify canonical internal values and aliases for:

- crypto_spot
- crypto_perpetual
- crypto_futures
- crypto_options
- forex
- commodity_spot
- commodity_future
- equity
- index
- equity_option
- future
- volatility
- yield
- macro
- synthetic/derived broker instruments
- analysis_only

Never classify a derivative as spot merely because its symbol ends in `USDT`.

## 7.2 Provider capability registry

Build a provider registry that declares:

- Supported asset classes.
- Supported market types.
- Supported timeframes.
- REST or WebSocket.
- Historical or live.
- Authentication requirement.
- Regional restrictions.
- Free-tier quota.
- Rate limit.
- Maximum bars.
- Delayed vs real-time.
- Adjusted vs raw prices.
- Corporate-action support.
- Open interest/funding/order book support.
- Health score.
- Circuit state.
- Current quota balance.
- Last successful fetch.
- Last failure category.
- Provenance confidence.

Verify current provider APIs and limits using official documentation. Do not trust old pasted quotas blindly. Respect provider terms and do not bypass rate limits.

Potential providers to evaluate and integrate only where valid:

### Public/free crypto and derivatives
- Coinbase Advanced Trade REST/WebSocket.
- OKX public REST/WebSocket.
- Kraken public REST/WebSocket.
- Binance spot/futures public REST/WebSocket, with regional-block handling.
- Bybit V5 spot/linear/inverse/options endpoints.
- Deribit futures/perpetual/options.
- CoinGecko for discovery/context, not primary low-latency execution truth.
- CryptoCompare as guarded fallback.
- CCXT only when its sync/async cost is acceptable.

### Multi-asset/key-based providers
- Alpha Vantage.
- Twelve Data.
- EODHD.
- Marketstack.
- Finnhub.
- FMP.
- Tiingo.
- Polygon.
- Alpaca.
- Tradier sandbox.
- OANDA practice.
- Nasdaq Data Link.
- Stooq.
- yfinance/Yahoo as a best-effort fallback, not sole production truth.
- Dukascopy/bulk historical sources for offline training and replay.
- MT5/MetaApi broker feeds.
- Deriv/MT5 where broker account access supports the instrument.

TradingView alerts are external signed signal inputs, not a substitute for verified market data.

## 7.3 Provider routing

Implement:

- Capability-aware order.
- Quota-aware routing.
- Token-bucket or leaky-bucket budgeting.
- Request coalescing.
- Cache reuse.
- Per-provider concurrency.
- Per-provider timeout.
- Circuit breakers.
- Exponential backoff with jitter.
- Provider quarantine after repeated bad data.
- Half-open recovery probes.
- Provenance on every candle and quote.
- Cross-provider sanity validation.
- Fallback only to providers capable of the requested asset/timeframe.
- No silent fallback from real-time to delayed data without marking it.
- No silent fallback from adjusted to unadjusted equity data.
- No provider result accepted when candle count, ordering, OHLC geometry, timestamp, volume, or freshness is invalid.

## 7.4 Market sessions and calendars

Use real timezone-aware calendars where available.

Handle:

- Crypto 24/7.
- Forex Sunday open to Friday close, holidays and rollover.
- Commodity-specific sessions.
- US and non-US stock exchanges.
- Regional indices.
- Futures sessions.
- daylight-saving changes.
- pre-market/after-hours where enabled.
- broker-specific synthetic indices separately.
- market holidays.
- early closes.

Do not use a fixed UTC−5 conversion for US markets.

## 7.5 WebSockets and tick-to-bar

Implement a guarded WebSocket supervisor with:

- Coinbase, OKX, Kraken, Binance, Bybit, or other verified routes.
- Provider-specific subscription limits.
- heartbeat.
- stale detection.
- reconnect with exponential backoff.
- circuit state.
- failover.
- no restart thrashing.
- tick deduplication.
- out-of-order timestamp handling.
- bounded buffers.
- tick-to-bar aggregation.
- completed-bar finalisation.
- partial-bar flags.
- sequence ordering per symbol/timeframe.
- REST gap backfill.
- data provenance.
- resource-pressure disabling.

WebSockets must not be required for correctness. REST should be capable of maintaining the system under degraded mode.

---

# 8. INDICATORS AND QUANTITATIVE MATH

Audit all indicators for mathematical correctness, input requirements, NaN handling, shape consistency, and look-ahead bias.

Implement or verify efficient versions of:

- EMA/SMA/WMA.
- RSI using Wilder smoothing.
- MACD and histogram.
- ATR and normalised ATR.
- ADX/DMI.
- Bollinger Bands.
- VWAP.
- volume profile/POC.
- realised volatility.
- z-score.
- momentum/ROC.
- OBV.
- stochastic.
- support/resistance.
- market structure.
- order blocks.
- liquidity sweeps.
- fair-value gaps.
- wick/body ratios.
- trend slope.
- beta/correlation.
- spread and liquidity metrics.
- order-book imbalance where available.
- funding/open interest/liquidation context for derivatives.

Do not replace mathematically correct existing indicator implementations with simplistic pasted examples. Add deterministic tests against known values.

Avoid loading pandas in the live hot path where NumPy or bounded arrays suffice. Keep pandas available for offline export/reporting only when needed.

---

# 9. STRATEGY AND SIGNAL ENGINE

Preserve the existing strategy inventory and complete missing implementations. The platform historically includes or requests:

- Trend following.
- Mean reversion.
- Breakout.
- Momentum.
- Scalping.
- Market structure.
- ICT.
- SMC.
- Order blocks.
- Liquidity sweeps.
- VWAP.
- Volume profile.
- Wyckoff.
- Grid.
- Pairs trading.
- Statistical arbitrage.
- Options flow where data exists.
- Macro.
- News.
- Institutional Momentum Pulse.
- Crypto liquidity squeeze/breakout.
- Forex session fade.
- Commodity value rotation.
- Equity macro trend/pullback.
- Multi-timeframe consensus.
- Regime-aware strategy selection.

For every strategy:

- Declare supported asset classes.
- Declare required timeframes.
- Declare minimum bars.
- Declare required provider capabilities.
- Version the strategy.
- Return structured candidate data.
- Return metrics used in scoring and ML telemetry.
- Never return geometrically invalid entry/SL/TP.
- Generate long and short where conceptually appropriate.
- Apply spread, liquidity, freshness, session, expected hold-time, and time-to-target checks.
- Avoid look-ahead bias.
- Include rejection reason and stage.
- Include risk profiles such as conservative, moderate, aggressive where product requirements support them.
- Include expiry policy.
- Include score provenance.
- Include evidence snapshot hash/version.

Use a deterministic strategy registry. One broken optional strategy must not crash the whole cycle.

---

# 10. SCORING, CALIBRATION, DEDUPLICATION, AND PORTFOLIO RISK

## 10.1 Scoring

Separate:

- Raw technical score.
- Regime alignment.
- Multi-timeframe alignment.
- Liquidity/spread quality.
- News context.
- On-chain context.
- ML probability.
- Gemini review.
- Provider confidence.
- delivery score.
- display score.

External AI or sentiment must not arbitrarily inflate a weak technical candidate. Gemini may explain or veto according to policy but must not invent market facts.

Cap display score at 99.5 while preserving raw internal values.

## 10.2 Expectancy

Remove hard-coded win/loss assumptions.

Calculate expectancy only from provenance-qualified samples:

- Delivered/live outcomes for live evidence.
- Paper outcomes for paper evidence.
- Shadow outcomes for shadow evidence.
- Backtest outcomes for backtest evidence.

Require configurable minimum sample size and confidence. Cache aggregate reads briefly. Do not turn missing data into zero expectancy.

## 10.3 Deduplication and cooldowns

Enforce:

- Full signal fingerprint.
- Asset/timeframe/direction/strategy deduplication.
- Active-asset lock.
- per-user asset repeat lock.
- delivered-only cooldown where required.
- in-flight reservation.
- provider/event idempotency.
- TradingView idempotency.
- broker-order idempotency.
- payment idempotency.

Database truth must repair Redis dedup state after Redis loss.

## 10.4 Portfolio exposure

Count only valid, non-expired, delivery-proven active signals for advisory exposure.

Do not count stored-but-never-delivered rows.

Use correct timezone handling.

On exposure-query failure:

- Advisory delivery may use a conservative Redis/database fallback according to explicit policy.
- Real execution must fail closed.

Apply:

- Max concurrent signals.
- Per-asset.
- Per-direction.
- Per-class.
- correlated exposure.
- sector/benchmark concentration.
- risk budget.
- account-margin constraints for execution.

---

# 11. TELEGRAM PRODUCT AND LOW-LATENCY DELIVERY

## 11.1 Telegram application

Audit every command and callback.

Ensure:

- All registered commands resolve.
- Every button has a callback handler.
- Immediate callback acknowledgement.
- No long DB/provider work before acknowledgement.
- Unknown callback logging.
- per-user error handling.
- role/tier gating.
- profile persistence.
- timezone/travel mode.
- pagination.
- support.
- reports.
- pricing.
- subscriptions.
- signals/history.
- outcome views.
- broker status.
- paper trading.
- admin/owner diagnostics.
- kill switches.

## 11.2 Webhook ingress

Webhook handler must:

- Validate secret/token/path.
- Return quickly.
- Enqueue durably to delivery Redis.
- Avoid slow processing inline.
- Enforce bounded worker count, default 4 for the one-service Hobby profile.
- Enforce queue size.
- Track pending, age, processing latency, retries, and dead letters.
- Handle duplicate Telegram updates idempotently.

## 11.3 Fan-out

Rebuild fan-out for multiple users:

- Preload eligible users, tiers, preferences, quotas, and prior deliveries in batches.
- Separate audience selection from network sends.
- Use bounded parallel Telegram sends.
- Respect per-chat and global rate limits.
- Honour RetryAfter precisely.
- Use reservation leases.
- Reconcile uncertain sends.
- Persist proof immediately after success.
- Do not hold a DB session during send.
- Extend or calculate queue expiry based on actual queued time, tier SLA, signal expiry, and market validity.
- Do not mark a valid signal `expired_in_queue` merely because a previous user send was slow.
- Preserve fairness.
- Avoid duplicate sends.
- Use delivery Redis for retries.
- Maintain dead-letter and manual reconciliation tools.

## 11.4 Exactly-once intent

Telegram cannot guarantee true exactly-once delivery. Implement exactly-once intent through:

- Redis `SET NX PX` reservation.
- Database unique constraints.
- User+signal delivery idempotency.
- explicit reservation state.
- sent state.
- uncertain state.
- reconciled state.
- terminal failed state.
- proof keys as accelerators, not sole truth.

---

# 12. SIGNAL LIFECYCLE AND OUTCOMES

Use one canonical state machine.

At minimum:

- CANDIDATE
- REJECTED
- STORED
- RESERVED
- SENT
- DELIVERED
- WATCHING_FOR_ENTRY
- ENTRY_TOUCHED
- ACTIVE
- TP1
- TP2
- TP3
- STOPPED
- MISSED_ENTRY
- EXPIRED
- CANCELLED
- INVALIDATED
- ARCHIVED

Enforce valid transitions atomically.

Protect against out-of-order ticks and concurrent workers.

Outcome tracking must:

- Use fresh provider data.
- Record provider and timestamp.
- Define same-candle TP/SL ambiguity policy.
- Track partial wins.
- Track early-exit recommendations separately from actual terminal outcome.
- Persist every transition.
- Update active Telegram messages.
- Send outcome notifications idempotently.
- Reconcile after restart.
- Never derive live performance from undelivered signals.

---

# 13. COMPLETE ML TELEMETRY AND LEARNING DATASET

## 13.1 Production philosophy

The Railway service must collect structured training data continuously but must not run memory-heavy live retraining by default.

Production responsibilities:

- Feature snapshot capture.
- candidate/rejection capture.
- lifecycle/outcome capture.
- MFE/MAE capture.
- provenance.
- export.
- lightweight inference with a pre-approved model.
- drift metrics that are bounded or scheduled.

Offline/local/GPU responsibilities:

- Large feature engineering.
- cross-validation.
- XGBoost/LightGBM training.
- hyperparameter search.
- SHAP.
- model comparison.
- calibration.
- walk-forward validation.
- model promotion.

Synthetic bootstrap data must never overwrite a production model or be labelled as live evidence.

## 13.2 Telemetry records

Do not create a simplistic duplicate table if existing models already cover these concepts. Extend the canonical schema.

Use typed indexed columns for common filters plus JSONB for versioned feature snapshots.

Capture every candidate, including:

- Delivered candidates.
- Rejected candidates.
- Near-miss candidates.
- Delayed candidates.
- Suppressed candidates.
- Quarantined candidates.
- Provider-invalid candidates.
- risk-blocked candidates.
- cooldown-blocked candidates.
- tier-ineligible candidates.
- Gemini-vetoed candidates.
- ML-blocked candidates.
- stale candidates.

### Identity and provenance

- telemetry ID.
- candidate ID.
- signal ID, nullable before storage.
- delivery ID, nullable.
- asset.
- canonical symbol.
- provider symbol.
- asset class.
- market type.
- exchange/venue.
- timeframe.
- strategy name.
- strategy version.
- feature-schema version.
- scoring-policy version.
- model version.
- prompt version.
- engine build/commit.
- direction.
- generated timestamp.
- market-data timestamp.
- rejection flag.
- rejection stage.
- rejection reason code.
- human-readable rejection detail.
- shadow-tracking eligibility.
- delivery-proof eligibility.
- evidence class.

### Market microstructure/environment

- entry candidate price.
- bid.
- ask.
- mid.
- spread absolute.
- spread bps.
- volume.
- quote volume.
- liquidity score.
- candle age.
- quote age.
- provider latency.
- fetch latency.
- normalised ATR.
- realised volatility.
- volatility regime.
- volume regime.
- trend regime.
- session.
- hour UTC.
- day of week.
- market-open state.
- minutes from open/close.
- benchmark asset.
- benchmark slope.
- rolling beta.
- rolling correlation.
- benchmark regime.
- broad market breadth where available.
- funding rate.
- open interest.
- open-interest change.
- liquidation imbalance.
- order-book imbalance.
- top-of-book depth.
- market-impact estimate.
- macro/news risk state.
- on-chain context.
- provider confidence.
- cross-provider disagreement.

### Technical setup

- raw strategy score.
- calibrated score.
- EMA values including EMA 200.
- percentage distance to EMA 200.
- VWAP.
- distance to VWAP.
- volume POC.
- distance to POC.
- RSI.
- MACD.
- MACD signal.
- MACD histogram.
- ADX.
- DMI.
- Bollinger width.
- momentum/ROC.
- wick/body ratio.
- upper wick/body ratio.
- lower wick/body ratio.
- body/range ratio.
- candle direction.
- support/resistance distances.
- order-block distances.
- liquidity-sweep flags.
- fair-value-gap context.
- MTF consensus.
- higher-timeframe trend.
- regime alignment.
- confluence counts.
- stop distance.
- TP distances.
- risk/reward ratios.
- expected hold time.
- expiry duration.
- time-to-target estimate.
- spread/slippage estimate.
- risk-gate outputs.
- AI/ML/news/on-chain component values.

### Delivery and operational telemetry

- stored timestamp.
- reservation timestamp.
- queue timestamp.
- send-start timestamp.
- Telegram success timestamp.
- queue wait milliseconds.
- Telegram latency milliseconds.
- delivery proof persisted timestamp.
- chat/message IDs present flag.
- delivery retries.
- RetryAfter count.
- delivery state.
- final quote drift.
- final validation result.
- suppressed due to resource pressure.
- DB admission wait.
- Redis latency.
- event-loop lag.
- resource-governor state.

### Outcome labels

Track more than TP/SL:

- terminal outcome.
- outcome provenance.
- entry touched timestamp.
- time to entry.
- TP1 timestamp.
- TP2 timestamp.
- TP3 timestamp.
- SL timestamp.
- expiry timestamp.
- missed-entry timestamp.
- duration minutes.
- MFE absolute.
- MFE percentage.
- MFE in R.
- MAE absolute.
- MAE percentage.
- MAE in R.
- highest favourable price.
- worst adverse price.
- percentage of distance to TP1 achieved.
- percentage of stop distance consumed.
- path efficiency.
- time under water.
- time in profit.
- slippage.
- spread paid/estimated.
- commissions/fees where applicable.
- realised R.
- partial-result R.
- early-exit recommendation and timestamp.
- counterfactual outcome under alternative targets/stops, clearly marked as counterfactual.
- stale/invalid outcome flag.

## 13.3 Rejected signals and shadow outcomes

Rejected candidates are a negative dataset and must not be lost.

Track eventual hypothetical outcomes only when:

- The candidate had valid market data.
- Entry/SL/TP geometry was valid.
- A defined shadow expiry exists.
- Provider provenance remains available.
- The outcome is marked `shadow`, never `live`.
- Shadow outcomes cannot contaminate live user performance.
- Rejection reasons are versioned.
- Sampling is controlled to avoid overwhelming the DB.
- The batch spool is used.

Track “3 out of 4 conditions passed” near-miss candidates, but do not limit telemetry only to those; record representative samples from every rejection class.

## 13.4 MFE and MAE implementation

For long signals:

- MFE is maximum high above entry.
- MAE is maximum low below entry.

For short signals:

- MFE is maximum favourable movement below entry.
- MAE is maximum adverse movement above entry.

Calculate absolute, percentage, and R-normalised values.

Update incrementally during lifecycle tracking using atomic/optimistic concurrency.

Do not scan the entire price history on every poll.

## 13.5 Export

Create a low-memory export command:

- Stream rows in chunks/server-side cursor.
- CSV and optionally Parquet.
- Date filters.
- asset class.
- strategy.
- evidence class.
- rejected/delivered.
- outcome.
- feature schema version.
- model version.
- anonymise user identifiers.
- output manifest.
- row count.
- checksum.
- schema JSON.
- no hard-coded DB URL.
- use existing DB settings.
- safe read-only priority.
- bounded memory.
- optional compression.

Do not use `fetchall()` for the full production table.

## 13.6 Offline training package

Create an offline training pipeline with:

- leakage audit.
- class balance report.
- time-based train/validation/test split.
- walk-forward validation.
- group separation by asset/time.
- baseline logistic model.
- XGBoost/LightGBM where installed.
- calibration.
- precision/recall.
- ROC-AUC and PR-AUC.
- Brier score.
- expectancy by probability bin.
- confusion matrix.
- feature importance.
- SHAP optional.
- drift comparison.
- model artifact.
- metadata.
- training data checksum.
- feature schema.
- promotion threshold.
- rollback.
- no automatic production promotion.

Model training must not optimise only win rate. Include expectancy, drawdown, MFE/MAE, time-to-resolution, and calibration.

---

# 14. GEMINI AND AI INTELLIGENCE

Complete the Gemini gateway:

- Official current SDK/API.
- timeout.
- retry only on appropriate errors.
- 429 Retry-After handling.
- global circuit breaker.
- cooldown persistence.
- bounded concurrency.
- daily/token budget.
- prompt version.
- structured JSON schema.
- validation.
- deterministic fallback.
- no repeated calls for the same candidate.
- cache.
- no blocking the delivery hot path.
- no fabricated market facts.
- explanation and veto policy.
- latency/cost metrics.

When Gemini is unavailable, deterministic strategies must continue if policy permits. AI unavailability must not crash the bot.

---

# 15. TRADINGVIEW WEBHOOKS

Restore or complete a real FastAPI TradingView endpoint that is not hidden by a root static mount.

Implement:

- Dedicated route.
- Authentication through secret/header/signature.
- Optional IP/rate control.
- strict payload schema.
- timestamp freshness.
- replay protection.
- idempotency key.
- asset symbol mapping.
- direction validation.
- entry/SL/TP geometry.
- RR threshold.
- allowed strategy/source.
- live quote drift validation.
- market session validation.
- Redis durable queue.
- immediate HTTP acknowledgement.
- database persistence.
- tier-aware delivery.
- audit log.
- dead-letter handling.
- test alerts.
- no direct bypass of risk, delivery proof, or portfolio controls.

---

# 16. MT5, METAAPI, COPY TRADING, AND EXECUTION

## 16.1 Broker abstraction

Use one broker interface supporting:

- account status.
- quote.
- symbol specification.
- balance/equity.
- margin.
- positions.
- orders.
- place order.
- modify.
- close.
- history.
- reconciliation.
- heartbeat.
- demo/live classification.

Adapters:

- MetaApi/hosted MT5 where configured.
- native MT5 terminal only where deployment environment genuinely supports it.
- paper broker.
- mock broker for tests.

Railway Linux cannot run the standard Windows MT5 terminal directly without an external bridge. Do not pretend native MT5 works inside Railway unless a valid remote/native architecture exists.

## 16.2 Execution gates

Require:

- global execution enabled.
- user execution enabled.
- tier eligibility.
- explicit current consent.
- credential encryption.
- account linked.
- demo/live policy.
- kill switch clear.
- daily loss limit.
- drawdown limit.
- open position limit.
- per-symbol limit.
- per-class limit.
- margin threshold.
- valid fresh quote.
- slippage limit.
- spread limit.
- symbol min/max/step.
- stop-level/freeze-level checks.
- market open.
- idempotency.
- resource pressure clear.
- provider/broker healthy.
- reconciliation available.

Real execution must fail closed.

## 16.3 Position sizing

Calculate from:

- account equity.
- configured risk percentage.
- entry/stop distance.
- contract size.
- tick size.
- tick value.
- currency conversion.
- broker lot step.
- broker minimum/maximum.
- margin.
- leverage.

Never use a fake balance or fallback lot.

## 16.4 Smart DCA

Repair and test Smart DCA:

- No hard-coded user/account.
- Use real user delivery proof.
- Use broker account metadata.
- Correct DCA step progression.
- correct async Redis APIs.
- per-user/per-signal idempotency.
- max additions.
- total risk cap.
- adverse movement criteria.
- no martingale.
- kill switch.
- demo-first.
- audit and reconciliation.

## 16.5 Copy trading

Build complete but gated:

- master/follower mapping.
- consent.
- proportional or fixed-risk mode.
- symbol mapping.
- account-currency conversion.
- max slippage.
- minimum lot constraints.
- partial failure handling.
- follower-specific risk limits.
- idempotency.
- reconciliation.
- opt-out.
- emergency stop.
- audit.
- demo mode.

---

# 17. PAYMENTS, SUBSCRIPTIONS, RECEIPTS, REFUNDS, AND REFERRALS

Complete Paystack safely:

- initiate.
- verify server-side.
- HMAC webhook verification.
- raw payload validation.
- event idempotency.
- amount/currency/product verification.
- transaction.
- entitlement activation.
- expiry/downgrade.
- receipt.
- refund.
- failed/pending states.
- reconciliation command/job.
- audit log.
- support lookup.
- referral rewards.
- extra-signal purchase.
- no trusting frontend success.
- public payment feature flag.
- test mode profile.
- production mode profile.

Payment webhook processing must remain operational during conservative resource mode.

---

# 18. PAPER TRADING, SHADOW MODE, BACKTESTING, AND REPLAY

## 18.1 Paper trading

Ensure complete:

- virtual accounts.
- configurable starting balance.
- positions.
- fills.
- fees.
- spread/slippage.
- pending orders.
- stop/targets.
- close.
- history.
- performance.
- reset.
- user isolation.
- no crossover into real broker state.

## 18.2 Shadow mode

- Process real-time candidates.
- Do not deliver or execute unless explicitly configured.
- Track hypothetical entry/outcomes.
- Include spread/slippage.
- preserve rejection reason.
- separate evidence.
- bounded sampling.
- proof-safe metrics.

## 18.3 Replay engine

Build a deterministic event replay engine:

- Historical candles/ticks.
- chronological ordering.
- configurable playback speed.
- sync or async callbacks.
- support strategy registry.
- no network dependency.
- fees and slippage.
- same lifecycle state machine where practical.
- result manifest.
- reproducible seed.
- no look-ahead.
- memory-bounded streaming.
- tests.

## 18.4 Backtesting

- Train/test separation.
- walk-forward.
- corporate-action adjustment for equities.
- survivorship-bias warnings.
- no using future bars.
- session handling.
- spread/fees.
- delisted-symbol handling where data permits.
- Monte Carlo or bootstrap robustness analysis offline.
- report provenance.

---

# 19. WEB/API AND ADMIN

Ensure the canonical FastAPI application includes:

- `/healthz`
- `/readyz`
- `/livez`
- metrics or diagnostic endpoint protected as needed.
- Telegram webhook.
- TradingView webhook.
- Paystack webhook.
- admin auth.
- owner auth.
- user/token APIs where used.
- dashboard/static mount after API routes or at a non-conflicting path.
- waitlist APIs/jobs.
- provider status.
- delivery debug.
- signal debug.
- broker status.
- payment status.
- resource status.

Restore the full FastAPI application if a small Flask replacement or stub has overwritten it.

Health semantics:

- `livez`: process/event loop alive.
- `healthz`: basic health, no expensive calls.
- `readyz`: required dependencies and migrations ready; fail when the service should not receive traffic.
- Optional deep diagnostic script for DB, both Redis instances, Telegram, providers, and broker.

Never put secrets in health output.

---

# 20. WAITLIST AND SCHEDULER

Fix missing waitlist scheduler jobs and verify imports.

Use one canonical scheduler.

Jobs must have:

- explicit owner.
- unique ID.
- coalesce.
- max instances.
- misfire grace.
- timeout.
- metrics.
- structured error category.
- no duplicate registration.
- no database session held between runs.
- role-based enablement.
- safe shutdown.

Verify:

- waitlist capacity.
- waitlist monitor.
- resends.
- free distribution.
- subscription downgrade.
- outcome notifications.
- signal expiry.
- active-message refresh.
- provider validation.
- cleanup.
- reconciliation.
- ML archive/backfill only when allowed.
- telemetry flush.
- state recovery checks.

Expected DB deferral is not a critical exception. Categorise it correctly.

---

# 21. OBSERVABILITY, HEALTH, AND INCIDENT RESPONSE

Implement structured JSON logging with:

- timestamp.
- level.
- component.
- event.
- trace/correlation ID.
- signal ID.
- delivery ID.
- user ID hashed/redacted where necessary.
- provider.
- asset.
- timeframe.
- latency.
- error category.
- retry count.
- resource state.

Do not log secrets, tokens, encrypted credentials, raw card/payment data, or broker passwords.

Metrics:

- Engine cycle duration.
- assets processed.
- candidates.
- rejections by reason.
- stored.
- reserved.
- sent.
- proof persisted.
- delivery latency.
- queue age.
- retries.
- uncertain sends.
- outcomes.
- provider latency/errors/circuit state.
- DB pool/admission metrics.
- Redis latency/pool/stream lag.
- event-loop lag.
- RSS.
- Gemini calls/429/circuit.
- broker orders/rejections/reconciliation.
- payment events/reconciliation.
- telemetry spool depth.
- active signals.
- lifecycle lag.

Provide:

- `scripts/production_health.py`
- `scripts/post_deploy_smoke.py`
- `scripts/live_production_evidence.py`
- `scripts/verify_owner_beta_release.py`
- provider smoke command.
- database/schema audit.
- Redis recovery test.
- deployment runbook.
- incident runbook.

Sentry or equivalent may be optional; configure filtering so expected network jitter is not treated like a code defect, while preserving critical events.

---

# 22. SECURITY

Audit and fix:

- secret handling.
- environment parsing.
- credential encryption.
- key rotation.
- Telegram webhook secret.
- TradingView secret/signature.
- Paystack HMAC.
- admin/owner role checks.
- IDOR.
- SQL injection.
- mass assignment.
- callback tampering.
- replay attacks.
- SSRF.
- unsafe URL fetching.
- path traversal.
- zip slip.
- command injection.
- logging leaks.
- open redirects.
- CORS.
- rate limiting.
- brute force.
- webhook body limits.
- request timeouts.
- dependency vulnerabilities.
- insecure deserialisation.
- unsafe pickle/model loading.
- model artifact signatures/checksums.
- broker consent audit.
- payment idempotency.
- PII retention.
- data export authorisation.

Use least privilege.

No remote code execution or autonomous deployment feature may be exposed through Telegram.

The Agent Council/CodexOps/Automaton may recommend actions but must not deploy, move funds, change production secrets, or bypass controls autonomously.

---

# 23. LATENCY IMPROVEMENT REQUIREMENTS

Reduce latency by architecture, not unsafe concurrency.

Implement:

- Immediate webhook ACK.
- Immediate callback ACK.
- Redis enqueue.
- request coalescing.
- quote/OHLC cache.
- batch DB reads.
- batch DB writes.
- no sessions across network calls.
- bounded concurrent fetches.
- provider-specific connection pooling.
- HTTP keep-alive.
- DNS reuse.
- optional timeframe fetch after required timeframe success.
- lazy imports.
- lazy model loading.
- no import-time network calls.
- precompiled format templates where useful.
- asynchronous Telegram sends.
- priority queues.
- critical vs background DB lanes.
- short caches for tier policy, preferences, expectancy and provider capabilities.
- reduced log verbosity in hot loops.
- no repeated Gemini call for same candidate.
- no repeated benchmark fetch per asset when one shared fetch can be reused.
- no repeated user query per signal.
- no repeated active-exposure query per candidate when one cycle snapshot is sufficient.
- no WebSocket restart loops.
- no busy-wait loops.
- adaptive cycle sleep.

Define and record latency SLOs, such as:

- Telegram webhook ACK p95 under 500 ms.
- callback ACK p95 under 500 ms.
- health endpoint p95 under 250 ms.
- delivery reservation p95 under 500 ms.
- candidate-to-send p95 according to timeframe and provider profile.
- DB admission wait bounded.
- provider timeout bounded.

Do not promise sub-millisecond execution on Railway Hobby.

---

# 24. ENVIRONMENT CONFIGURATION

Generate:

1. `.env.example`
2. `configs/env/railway-hobby-full-advisory.env.example`
3. `configs/env/railway-hobby-owner-beta.env.example`
4. `configs/env/railway-hobby-paper-demo.env.example`
5. `configs/env/railway-hobby-real-execution-gated.env.example`
6. optional future role profiles.

Every variable must include:

- purpose.
- default.
- valid range.
- whether secret.
- whether safe for production.
- dependencies.
- conflicts.

Base safe values should include or reconcile with the code:

```env
PUBLIC_TESTING_MODE=0
AUTO_MIGRATE=0

DB_POOL_SIZE_RAILWAY=2
DB_MAX_OVERFLOW_RAILWAY=0
DB_POOL_TIMEOUT_SECONDS=15
DB_MAX_CONCURRENT_SESSIONS=2

REDIS_MAX_CONNECTIONS=24

UVICORN_WORKERS=1
WEBHOOK_UPDATE_WORKERS=4
WEBHOOK_UPDATE_QUEUE_SIZE=1000

ENGINE_UNIVERSE_CAP=18
CYCLE_BATCH_SIZE=6
MARKET_FETCH_ASSET_CONCURRENCY=2
MARKET_CACHE_FETCH_CONCURRENCY=2

RESOURCE_GUARD_ENABLED=1
APP_MEMORY_LIMIT_MB=0
APP_MEMORY_SOFT_RATIO=0.72
APP_MEMORY_HARD_RATIO=0.88
APP_MEMORY_RECOVERY_MARGIN_MB=32

PORTFOLIO_EXPOSURE_REQUIRE_DELIVERED=1
SEGMENT_QUARANTINE_REQUIRE_DELIVERED=1
SEGMENT_QUARANTINE_MIN_TRADES=30
ASSET_REPEAT_LOCK_REQUIRE_DELIVERED=1

RESEND_SKIP_WHEN_CRITICAL_DB_ACTIVE=0
DB_BACKGROUND_JOBS_SKIP_WHEN_CRITICAL_ACTIVE=0

ML_OFFLINE_BOOTSTRAP_ENABLED=0
ML_TRAIN_ENABLED=0
ANALYTICS_ML_TRAIN_ENABLED=0
ML_DRIFT_MONITOR_ENABLED=0

AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
MT5_ALLOW_LIVE_ACCOUNTS=0
```

`APP_MEMORY_LIMIT_MB=0` should auto-detect cgroup/container limits when possible. Allow an explicit override.

Full advisory features may be enabled after verification. Heavy training remains off in the live monolith.

Provide separate variables for every provider API key and quota. Missing optional keys must not prevent startup.

---

# 25. STARTUP AND RAILWAY DEPLOYMENT

Use one canonical start path.

Expected form:

```bash
exec uvicorn railway_main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --workers 1
```

The actual module must be determined from the repository.

`start.sh` must:

- `set -euo pipefail`.
- print build/version.
- run a fast release guard.
- not run the full test suite at every boot.
- optionally run migration only when explicitly enabled.
- use `exec` so signals reach Uvicorn.
- support graceful shutdown.
- not spawn duplicate workers.
- not expose secrets.
- fail fast on invalid production env.

Provide a minimal Dockerfile or Railway Nixpacks configuration:

- pinned Python version.
- deterministic dependencies.
- no pip cache.
- non-root user where compatible.
- health check.
- no unnecessary build tools in final image.
- lazy optional heavy dependencies.
- correct timezone/data packages.
- correct Uvicorn worker count.

Deployment guide must include:

1. PostgreSQL creation.
2. PgBouncer URL selection.
3. Redis 1 creation.
4. Redis 2 creation.
5. variable mapping.
6. Telegram webhook domain.
7. Paystack webhook.
8. TradingView webhook.
9. provider keys.
10. MetaApi/MT5 variables.
11. encryption key generation.
12. one-time migration.
13. migration rollback/recovery.
14. health checks.
15. smoke tests.
16. owner-only soak.
17. staged asset-class activation.
18. staged public release.
19. logs to watch.
20. rollback procedure.

---

# 26. SPECIFIC PREVIOUSLY FOUND DEFECTS TO RE-AUDIT

Even if the current repository appears to include fixes, explicitly verify these regressions:

1. Portfolio exposure naïve/aware datetime mismatch.
2. Stored-but-undelivered signals counted as exposure.
3. Redis-empty state mass-expiring PostgreSQL signals.
4. Segment quarantine contaminated by undelivered outcomes.
5. Gemini 429 circuit cooldown not persisting.
6. `decision_log.created_at` missing.
7. synthetic ML bootstrap overwriting production model.
8. background DB work skipped globally during critical work.
9. rejection logs dropped under DB pressure.
10. WebSocket provider restart thrashing.
11. stale-signal learning calling `persist_rejection()` on the wrong class.
12. `web/app.py` replaced by a small Flask app instead of the required FastAPI app.
13. root static mount intercepting TradingView webhook.
14. TradingView handler referencing undefined functions.
15. waitlist jobs unavailable/import broken.
16. MetaApi execution proceeding without live quote.
17. account-information retrieval referenced but missing.
18. risk percentage not loaded from DB.
19. fallback `0.01` lot.
20. Bybit incorrect endpoint/category handling.
21. derivative symbols classified as spot.
22. Smart DCA nonexistent MT5 import.
23. Smart DCA awaiting synchronous Redis methods or calling wrong async APIs.
24. Smart DCA unable to progress DCA1→DCA2.
25. Smart DCA hard-coded user/account.
26. `REDIS_MAX_CONNECTIONS` effectively 200.
27. hard-coded expectancy averages.
28. unsafe native MT5 bridge with fake balance.
29. `long` direction interpreted incorrectly.
30. broker login config unused.
31. missing trade geometry validation.
32. queue expiry causing later users to receive `expired_in_queue`.
33. fan-out N+1 user/preferences/tier queries.
34. full ML/XGBoost stack imported on live startup.
35. local `telegram/` package shadowing `python-telegram-bot`.
36. `datetime.utcnow()` inconsistency in runtime code.
37. disabled ML archive job still consuming startup work.
38. provider fallback accepting delayed or stale data as live.
39. callback buttons not responding.
40. Supplied signal/outcome tracking not proving the same signal ID through the lifecycle.

Add regression tests for every confirmed issue.

---

# 27. TESTING AND VERIFICATION

## 27.1 Required test categories

- Unit.
- Async.
- integration with local/mocked dependencies.
- database contract.
- migration.
- PgBouncer compatibility.
- Redis stream.
- queue recovery.
- provider adapters.
- provider fallback.
- rate limit.
- circuit breaker.
- market sessions.
- indicators.
- strategies.
- scoring.
- risk.
- dedupe.
- exposure.
- Telegram command registration.
- callback routing.
- delivery idempotency.
- Telegram RetryAfter.
- uncertain send.
- lifecycle.
- MFE/MAE.
- rejected telemetry.
- export streaming.
- model artifact safety.
- TradingView webhook.
- Paystack webhook.
- MT5/MetaApi.
- Smart DCA.
- copy-trading guards.
- paper trading.
- resource governor.
- health endpoints.
- startup.
- scheduler ownership.
- security.
- architecture.
- secrets.
- performance/bounded queues.

## 27.2 Complete lifecycle test

Create a real contract test, not booleans hard-coded to `True`.

The test must use repositories/fakes to prove:

1. candidate creation.
2. storage.
3. delivery reservation.
4. fake Telegram success.
5. `sent_ok`.
6. chat/message ID persistence.
7. active-message persistence.
8. `WATCHING_FOR_ENTRY`.
9. entry touch.
10. active state.
11. TP/SL/expiry terminal transition.
12. MFE/MAE update.
13. outcome notification.
14. no duplicate notification.
15. restart recovery.

## 27.3 Full-suite execution

Run:

- compileall.
- import audit.
- lint if configured.
- type check if configured.
- all tests.
- If full suite exceeds timeout, run all test files in deterministic bounded groups and aggregate counts.
- Do not omit slow tests silently.
- schema audit.
- migration head.
- architecture boundaries.
- DB session API audit.
- secret scan.
- dependency audit where available.
- environment profile validation.
- ZIP CRC.
- checksum.

Document skipped tests and exact reasons.

## 27.4 Production smoke

Where live secrets are unavailable, create scripts. On Railway, require:

- `/livez` success.
- `/healthz` success.
- `/readyz` success.
- both Redis pings.
- PostgreSQL query.
- Telegram `getMe`.
- webhook status.
- provider sample by asset class.
- TradingView test alert.
- Paystack test event.
- MetaApi demo account status.
- one natural signal lifecycle proof.
- restart recovery proof.

---

# 28. PERFORMANCE AND SCALE TESTS

For one Railway Hobby service, test realistic bounded workloads rather than claiming 100,000-user live fan-out is proven.

Required local simulations:

- 100,000-user audience selection with zero duplicates/omissions.
- Batched preference/tier loading.
- bounded fan-out scheduling.
- delivery reservation uniqueness.
- Telegram rate-limit simulation.
- queue expiry.
- DB pool size 2.
- rejection telemetry burst.
- Redis stream lag.
- provider outage.
- WebSocket outage.
- Redis wipe/recovery.
- process restart.
- resource pressure.
- 1,000 simultaneous callback updates through queue.
- payment replay.
- TradingView replay.
- broker duplicate order request.

Report:

- memory.
- p50/p95/p99 latency.
- queue depth.
- DB waits.
- retries.
- data loss.
- duplicates.
- recovery time.

Do not claim Railway live capacity solely from local simulation.

---

# 29. REQUIRED DELIVERABLES

Return all of the following:

1. Complete updated repository ZIP.
2. Git patch from supplied baseline.
3. Full change report.
4. Updated master project document or addendum.
5. Updated `.env.example`.
6. Railway Hobby full-advisory env profile.
7. Railway owner-beta env profile.
8. paper/demo profile.
9. gated execution profile.
10. migration files.
11. schema diagram/catalogue update.
12. provider capability matrix.
13. command/callback catalogue.
14. feature/status matrix.
15. production deployment runbook.
16. rollback runbook.
17. incident runbook.
18. test evidence.
19. live acceptance checklist.
20. unresolved external blockers.
21. SHA-256 checksums.
22. exact repository root/start command.
23. exact Railway variables to add, remove, and modify.
24. exact secrets the owner must supply.
25. exact activation sequence.

Do not return only snippets. Do not omit unchanged files from the full ZIP.

---

# 30. REQUIRED IMPLEMENTATION WORKFLOW

Use this sequence:

## Pass 1 — Forensic baseline

- Extract.
- inventory.
- run tests.
- inspect logs.
- inspect Git.
- map architecture.
- establish current truth.
- list contradictions.

## Pass 2 — Critical runtime truth

Fix:

- startup.
- FastAPI.
- database.
- migrations.
- timezone.
- Redis recovery.
- delivery proof.
- lifecycle.
- callbacks.
- waitlist.
- signal storage/delivery.

## Pass 3 — Resource and latency

Fix:

- admission control.
- batching.
- Redis pools.
- queues.
- fan-out.
- webhook ACK.
- callback ACK.
- lazy imports.
- provider coalescing.
- resource governor.
- degradation.

## Pass 4 — Multi-asset providers

Implement and test provider registry/routing, sessions, derivatives, quotas, provenance and failover.

## Pass 5 — Strategies and intelligence

Complete indicators, strategies, scoring, risk, expectancy, news, on-chain, AI and calibration.

## Pass 6 — Telemetry and outcomes

Complete ML telemetry, rejection dataset, shadow outcomes, MFE, MAE, duration, export and offline training.

## Pass 7 — Product features

Complete Telegram UX, payments, referrals, paper, reports, admin, TradingView, subscriptions, support and waitlist.

## Pass 8 — Broker execution

Complete paper, demo, MetaApi, native bridge constraints, Smart DCA, copy trading, risk, reconciliation and kill switches.

## Pass 9 — Security and operations

Complete auth, secrets, webhooks, observability, health, runbooks, cleanup and incident handling.

## Pass 10 — Verification and packaging

Run all gates, fix failures, rerun, package, checksum and produce the final evidence report.

After every pass:

- Run focused tests.
- Inspect diff.
- Remove accidental noise.
- Update living registers/docs.
- Do not proceed while a critical regression remains.

---

# 31. DEFINITION OF DONE

Do not declare completion until all code-verifiable conditions pass:

- One canonical FastAPI app.
- One canonical DB session API.
- One migration head.
- Clean compile.
- No missing imports.
- No undefined callbacks.
- No `pass` placeholders in production paths.
- No hard-coded production user/account/balance.
- No fake live market data.
- No synthetic production ML overwrite.
- No unsafe lot fallback.
- No duplicate scheduler ownership.
- No Redis-as-authority failure.
- No mass expiration on empty Redis.
- No stored-only exposure contamination.
- No undelivered performance contamination.
- No unbounded queue.
- No unbounded concurrency.
- No DB session across network I/O.
- No WebSocket restart thrashing.
- No repeated Gemini 429 hammering.
- No callback timeout.
- No unverified TradingView bypass.
- No payment replay.
- No broker duplicate order.
- Telemetry batching works.
- Rejected signals are tracked.
- MFE/MAE works.
- export is streaming and bounded.
- health/readiness semantics work.
- state recovers after Redis wipe.
- tests pass or documented external tests remain.
- deployment files match code.
- exact Railway instructions are complete.

Production/public release must still be marked blocked when live evidence is missing. The final verdict must distinguish:

- Locally verified.
- Railway deployed.
- Owner-beta proven.
- Limited public proven.
- Paid beta proven.
- Real execution proven.

---

# 32. FINAL RESPONSE FORMAT

Your final response must include:

## A. Executive verdict

State exactly what is complete and what still requires live proof.

## B. Major issues found

Rank by critical/high/medium/low and include root cause.

## C. Code changes

List files and behaviours changed.

## D. Verification

Include commands and exact pass/fail counts. Do not merge counts from different snapshots.

## E. Downloadable artifacts

Link the complete ZIP, patch, report, env profiles and checksums.

## F. Railway deployment

Give exact numbered steps and exact start command.

## G. Environment variables

Provide:

- Add.
- Change.
- Remove.
- Secrets to supply.
- Owner-beta values.
- full advisory values.
- demo execution values.
- real execution gated values.

## H. Activation order

1. Deploy core advisory.
2. Migrate.
3. Verify health.
4. Prove Telegram lifecycle.
5. Run owner soak.
6. Enable asset classes progressively.
7. Enable optional WebSockets.
8. Enable payments in test mode.
9. Enable public advisory.
10. Enable paper/demo broker.
11. Collect at least 100 delivery-proof live outcomes.
12. Export/train offline.
13. promote validated inference model.
14. separately approve real execution.

## I. Known external limitations

List provider quotas, missing credentials, Railway single-replica downtime, broker limitations and anything not reproducible locally.

---

# 33. IMPORTANT BEHAVIOURAL INSTRUCTIONS

- Do not ask broad questions already answered by the repository or documents.
- Make grounded assumptions only when harmless and document them.
- Ask only when a missing secret or irreversible business decision blocks implementation.
- Do not replace complex working components with toy examples.
- Do not merely paste the code examples from the notes.
- Do not bypass provider limits, regional restrictions, or terms of service.
- Do not use unofficial scraping when it creates unacceptable legal or reliability risk without flagging it.
- Do not run destructive migrations without backup and explicit migration steps.
- Do not delete production data.
- Do not expose secrets.
- Do not turn off safety gates to make tests pass.
- Do not lower quality thresholds merely to increase signal frequency.
- Do not mark a test as passed without running it.
- Do not claim external integrations work without live evidence.
- Do not stop after the first successful signal.
- Do not optimise only for win rate.
- Do not allow rejected/shadow/backtest results to contaminate live performance.
- Do not enable real execution merely because code compiles.

Begin by inspecting every supplied source and repository file. Then execute the ten-pass workflow until the project reaches the strongest honest completion state possible.
---

# 34. UNIVERSAL SIGNALRANKAI REQUIREMENT COVERAGE, CROSS-CHAT RECONSTRUCTION, DEEP WEB RESEARCH, PROVIDER CERTIFICATION, AND PROFILE VERIFICATION

This section is mandatory and overrides any narrower interpretation elsewhere in this prompt.

## 34.1 Cover every major and minor SignalRankAI requirement

Do not restrict the audit to headline features, current errors, or the contents of the latest master document. Reconstruct the complete product specification from every available source and capture:

- Major product requirements.
- Minor product requirements.
- Small user-experience details.
- Historical defaults.
- Compatibility aliases.
- previously discussed edge cases.
- deferred improvements.
- feature ideas that were accepted but never implemented.
- behaviour that exists in one code path but not another.
- buttons, messages, commands, scheduler jobs, environment flags, database fields, API endpoints, admin controls, reports, provider adapters, broker functions, and background workflows.
- requirements expressed informally in chat, logs, screenshots, reports, issue descriptions, pasted text, documentation, tests, migrations, comments, Git history, or environment files.

Create a **Universal Requirement Register** before implementation. Every requirement must have:

- Requirement ID.
- Source.
- Exact wording or faithful paraphrase.
- Category.
- Priority.
- Current implementation location.
- Current status: complete, partial, broken, absent, duplicated, obsolete, unverified, externally blocked.
- Dependencies.
- Acceptance test.
- Final evidence.
- Deferred reason, if any.

Do not silently omit a requirement because it appears small, old, duplicated, difficult, expensive, or inconvenient.

## 34.2 Reconstruct all SignalRankAI chats

Before changing code:

1. Search every historical conversation, transcript, exported chat, uploaded report, pasted note, project document, and previous assistant response that relates to:
   - SignalRankAI.
   - SignalRankAI1.
   - the Telegram trading bot.
   - the trading ecosystem.
   - signals, providers, outcomes, delivery, ML, Telegram, MT5, MetaApi, Paystack, TradingView, paper trading, copy trading, referrals, profiles, tiers, Railway, Postgres, Redis, or production readiness.

2. Build a **Cross-Chat Decision Ledger** containing:
   - accepted decisions.
   - superseded decisions.
   - conflicting decisions.
   - exact numeric defaults.
   - user preferences.
   - constraints.
   - unfinished promises.
   - bugs previously reported.
   - features previously requested.
   - features believed to be implemented but not yet proven.

3. Use the latest explicit user decision when requirements conflict.

4. Preserve older compatibility behaviour only when it does not contradict the current canonical policy.

5. Do not claim “all chats reviewed” unless the historical chats or exports were actually available and searched.

6. When direct access to earlier chats is unavailable:
   - inspect all supplied exports and project documents;
   - list the unavailable sources;
   - state that cross-chat coverage is incomplete;
   - do not invent missing decisions;
   - request only the missing export when it blocks correctness.

7. Compare the reconstructed Cross-Chat Decision Ledger against:
   - repository code.
   - database schema.
   - environment variables.
   - tests.
   - Telegram command registration.
   - callback registration.
   - provider registry.
   - strategy registry.
   - scheduler registry.
   - deployment profiles.
   - master documentation.

Any requirement that exists in discussion but not in code becomes an implementation task. Any feature claimed in documentation but unreachable or untested becomes a defect.

## 34.3 Mandatory feature-discovery audit

Do not assume the user has remembered every required feature.

Study the project as a product, trading system, SaaS platform, Telegram application, data platform, broker platform, payment platform, ML system, and production service. Identify missing capabilities required for correctness, safety, maintainability, competitive quality, or real user operation.

Run a systematic gap analysis across:

- Product onboarding.
- Authentication and identity.
- Roles and tiers.
- Profiles and preferences.
- Telegram UX.
- Accessibility and localisation.
- Notification controls.
- Signal creation.
- Data ingestion.
- Data quality.
- Strategies.
- Scoring.
- portfolio risk.
- outcomes.
- ML telemetry.
- reporting.
- paper trading.
- backtesting.
- shadow mode.
- broker linking.
- execution.
- payments.
- subscriptions.
- referrals.
- support.
- administration.
- audit.
- privacy.
- security.
- observability.
- recovery.
- migrations.
- deployment.
- documentation.
- testing.
- cost control.
- provider quotas.
- incident response.

For every newly discovered gap:

- Explain why it is needed.
- Identify competitors or established system patterns that support the need.
- Determine whether it belongs in the current release or a later governed phase.
- Implement it when required for a coherent production product.
- Add tests and documentation.
- Do not add speculative complexity that cannot operate on the target Railway plan.

## 34.4 Deep web research is mandatory

Use current web research before finalising architecture, provider adapters, quotas, SDK usage, market sessions, broker integration, payment behaviour, Telegram behaviour, Railway deployment, security configuration, and dependency versions.

Research rules:

- Prefer official documentation, official API references, official SDK repositories, official status pages, exchange specifications, broker documentation, Railway documentation, Telegram Bot API documentation, Paystack documentation, MetaApi documentation, TradingView webhook documentation, and primary research papers.
- Use secondary sources only to discover topics or compare opinions; verify technical claims against primary sources.
- Record the research date.
- Record source URLs in the project research register.
- Record API version.
- Record deprecation status.
- Record free-tier restrictions.
- Record real-time versus delayed status.
- Record regional limitations.
- Record authentication requirements.
- Record allowed usage and redistribution restrictions.
- Record symbol conventions.
- Record market-session rules.
- Record rate limits.
- Record WebSocket limits.
- Record maximum historical depth.
- Record required attribution.
- Record data-quality limitations.
- Record licensing or commercial-use concerns.
- Record whether the source is appropriate for analysis, delivery, execution validation, backtesting, or discovery only.

Do not copy claims from AI-generated provider lists without verification.

Do not implement deprecated endpoints.

Do not bypass rate limits, geographical restrictions, authentication, or provider terms.

Do not claim that a free provider offers real-time data when the official plan is delayed.

## 34.5 Provider implementation and certification

Every provider included in the final production registry must be fully implemented, not merely named.

For each provider, implement and verify:

- Capability declaration.
- Asset classes.
- Market types.
- Timeframes.
- REST endpoints.
- WebSocket endpoints where applicable.
- symbol mapper.
- timeframe mapper.
- authentication.
- request signing where applicable.
- quota accounting.
- rate limiting.
- concurrency limits.
- timeout.
- retry classification.
- circuit breaker.
- half-open recovery.
- response parsing.
- pagination.
- candle ordering.
- duplicate handling.
- timezone conversion.
- OHLC geometry validation.
- volume validation.
- freshness validation.
- delayed-data marking.
- adjusted/unadjusted marking.
- market-session compatibility.
- provenance.
- health metrics.
- structured errors.
- cache policy.
- fallback eligibility.
- unit tests.
- fixture tests.
- malformed-response tests.
- timeout tests.
- 429 tests.
- 5xx tests.
- unknown-symbol tests.
- empty-data tests.
- stale-data tests.
- live sandbox or public endpoint smoke test where legally and technically possible.

Create a **Provider Certification Matrix** with these statuses:

- IMPLEMENTED_AND_LIVE_VERIFIED
- IMPLEMENTED_AND_SANDBOX_VERIFIED
- IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED
- IMPLEMENTED_AND_MOCK_VERIFIED
- BLOCKED_MISSING_CREDENTIAL
- BLOCKED_REGION
- BLOCKED_ACCOUNT_APPROVAL
- BLOCKED_PAID_PLAN
- DEPRECATED
- UNSUITABLE_FOR_PRODUCTION
- ANALYSIS_ONLY
- DISABLED

A provider must not be enabled in production merely because mock tests pass.

Missing optional provider credentials must not prevent the platform from starting.

Required provider tests must fail clearly rather than silently skip when a production profile declares that provider required.

## 34.6 Provider families to research and certify

At minimum, study the current official documentation and determine the correct production role for:

### Crypto spot, futures, perpetuals, and options

- Coinbase Advanced Trade.
- OKX.
- Kraken.
- Binance spot.
- Binance futures.
- Bybit V5 spot.
- Bybit linear/inverse derivatives.
- Bybit options.
- Deribit.
- KuCoin.
- CoinGecko.
- CryptoCompare.
- CCXT-supported public exchange feeds where appropriate.

### Stocks, indices, forex, commodities, options, futures, and macro

- Alpha Vantage.
- Twelve Data.
- EODHD.
- Marketstack.
- Finnhub.
- Financial Modeling Prep.
- Tiingo.
- Polygon.
- Alpaca.
- Tradier.
- OANDA practice.
- Stooq.
- Nasdaq Data Link.
- yfinance/Yahoo.
- Dukascopy historical data.
- official exchange or broker feeds where available.
- MT5/MetaApi broker feeds.
- Deriv broker instruments where the linked MT5 account exposes them.

Do not force every provider into the live routing chain. A correctly completed implementation may classify some as:

- primary.
- fallback.
- discovery-only.
- analysis-only.
- historical-only.
- broker-validation-only.
- sandbox-only.
- disabled due to quota, delay, terms, region, or reliability.

The requirement is that every selected/supported provider is correctly implemented and honestly classified—not that all providers are called during every engine cycle.

## 34.7 Trader profiles must work end to end

The canonical trader profiles are:

- `scalp`
- `day`
- `swing`
- `position`
- `all`

Verify each profile across:

- Telegram onboarding.
- profile menu.
- callback buttons.
- database persistence.
- API representation.
- defaults.
- validation.
- migration compatibility.
- engine selection.
- timeframe selection.
- strategy eligibility.
- expiry.
- time-to-target.
- spread limits.
- liquidity limits.
- session filters.
- notification policy.
- delivery policy.
- risk guidance.
- outcome tracking.
- reporting.
- resend logic.
- history filters.
- paper trading.
- broker execution eligibility.
- tests.

Profile behaviour requirements:

### Scalp

- Shortest supported timeframes.
- strictest freshness.
- strictest spread and liquidity limits.
- strict session and latency requirements.
- short expiry.
- rapid outcome checks.
- no illiquid or delayed provider data.
- no delivery when queue latency makes the setup invalid.

### Day

- Supported intraday timeframes.
- signal should normally be capable of reaching an outcome within one trading day.
- session-aware expiry.
- overnight exposure policy.
- time-to-target validation.
- session-transition risk controls.

### Swing

- Higher-timeframe context.
- longer expiry.
- lower sensitivity to short-term noise.
- weekend/holiday handling by asset class.
- fresh final quote still required.

### Position

- Higher-timeframe trend and macro context.
- longest governed expiry.
- corporate events, rollover, funding, and macro risk where applicable.
- no use of an intraday-only provider for long-horizon evidence without adequate history.

### All

- Correct union of supported profiles.
- No duplicated delivery.
- No bypass of risk or tier rules.
- User can still filter assets, timeframes, strategies, and sessions.

Profile changes must affect subsequent eligibility immediately and persist across restarts.

## 34.8 Exact canonical user tiers

The canonical tiers are:

- `free`
- `premium`
- `vip`
- `admin`
- `owner`

Verify:

- onboarding.
- entitlement.
- score bands.
- daily limits.
- preference access.
- reports.
- broker features.
- admin controls.
- owner controls.
- payment transitions.
- expiry/downgrade.
- aliases.
- existing-user migrations.
- tests.

Do not invent subscription prices or periods. Recover the latest accepted weekly/monthly pricing policy from the conversations or current product configuration. When unavailable, preserve current values and flag the business decision.

## 34.9 Canonical timeframes and cooldown rules

Verify and implement the canonical signal timeframes:

- `5m`
- `15m`
- `1h`
- `4h`
- `1d`

Support broader horizons only when required by a verified strategy/profile and supported by providers.

Preserve or explicitly reconcile these historical cooldown defaults:

- 15m: 10 minutes.
- 1h: 20 minutes.
- 4h: 90 minutes.
- 1d: 6 hours.

Implement the explicit per-user asset delivery lock:

- Default four hours after a successfully delivered signal for the same asset.
- It must be delivery-proof based.
- It must not be triggered by a stored-but-undelivered signal.
- Active-position locking and full fingerprint deduplication still apply.
- Make the value configurable.
- Add migration/config compatibility.
- Add tests.

If the current canonical business policy differs, document the conflict and use the latest explicit decision.

## 34.10 Market hours and user notifications

Implement market-session behaviour end to end:

- Tell users when a requested market or asset is closed.
- Show the expected reopen time using the user’s timezone.
- Respect daylight-saving time and holidays.
- Show which session is being monitored.
- Avoid presenting closed-market stale candles as current.
- Provide session filters in profiles.
- Notify only according to user preferences.
- Keep crypto 24/7 handling separate from traditional markets.
- Handle broker synthetic indices according to broker-specific schedules, not equity calendars.

## 34.11 Early-exit and opportunity-change intelligence

Implement governed early-exit warnings:

- Detect meaningful invalidation before SL.
- Detect volatility collapse.
- detect loss of structure.
- detect liquidity deterioration.
- detect adverse news/macro context.
- detect correlated-market breakdown.
- detect provider/data uncertainty.
- distinguish recommendation from actual outcome.
- record the reason and timestamp.
- avoid repeatedly alerting the same condition.
- allow user notification preferences.
- never rewrite SL history to make a recommendation look like a win.
- keep early-exit performance as a separate evidence category.

## 34.12 Exact outcome semantics

Preserve the accepted performance interpretation:

- Individual TP milestones are recorded as wins according to the canonical reporting policy.
- SL is a loss.
- Partial TPs are recorded separately and contribute correct realised/partial R.
- missed entries are not wins or losses.
- expired signals are not wins or losses unless a separately defined methodology says otherwise.
- users receive missed-entry and expiry notifications.
- shadow outcomes are included only in shadow reports.
- live, delivered, paper, shadow, backtest, walk-forward, demo, and real-execution performance remain separate.
- include spread, slippage, fees, and latency where relevant.

Do not optimise reports to make the displayed win rate look better.

## 34.13 Every command, callback, button, message, and workflow

Treat every command as broken until verified.

Build a machine-readable catalogue of:

- command.
- aliases.
- required role.
- required tier.
- feature flag.
- handler.
- callback routes.
- response template.
- database dependencies.
- external dependencies.
- tests.
- production verification status.

Exercise:

- all Telegram commands.
- unknown-command handling.
- every inline button.
- nested menus.
- pagination.
- profile selection.
- filters.
- broker flows.
- payment flows.
- receipts.
- support.
- admin.
- owner tools.
- outcome buttons.
- paper-trade buttons.
- upgrade/referral buttons.
- callback expiry.
- tamper handling.
- duplicate presses.
- restart behaviour.

Every callback must acknowledge promptly and remain idempotent.

Upgrade every user-facing message for:

- clarity.
- correctness.
- truthful evidence labels.
- tier context.
- actionable errors.
- consistent formatting.
- no misleading confidence.
- localisation readiness.
- compatibility with Telegram length and Markdown/HTML rules.

## 34.14 Continuous improvement and feature discovery

Implement a governed feature-discovery and improvement register, not autonomous unrestricted code deployment.

The system may:

- collect feature gaps.
- collect user feedback.
- collect recurring failures.
- rank improvements.
- generate read-only engineering recommendations.
- identify poor-performing strategies.
- identify provider weaknesses.
- identify UX friction.
- create audit reports.

The system must not:

- deploy code autonomously.
- alter production secrets.
- enable real execution autonomously.
- move money autonomously.
- lower risk controls autonomously.
- modify evidence.
- promote an ML model without approval.

## 34.15 Cross-source completeness gate

Before declaring the project complete, produce:

1. Universal Requirement Register.
2. Cross-Chat Decision Ledger.
3. Feature Coverage Matrix.
4. Provider Certification Matrix.
5. Trader Profile E2E Matrix.
6. Tier E2E Matrix.
7. Command/Callback/Button Matrix.
8. Strategy Coverage Matrix.
9. Asset-Class Coverage Matrix.
10. Environment Variable Contract.
11. External Blocker Register.
12. Gap Closure Report.

Completion is blocked when:

- A known requirement has no implementation status.
- A registered command has no test.
- A visible button has no handler.
- A selected provider has no certification status.
- A trader profile does not affect engine/delivery behaviour.
- A tier is not enforced consistently.
- documentation claims a feature that code cannot reach.
- code contains an enabled feature omitted from documentation.
- a production provider is only mock-tested.
- a missing chat/source prevents recovery of a material business rule.
- unresolved critical/high defects remain.
- external live proof is missing but the release is labelled fully proven.

## 34.16 Final honesty rule

The implementation must pursue the strongest possible production readiness, but it must never use the phrase “100% production ready” as a substitute for evidence.

The final report must state separately:

- all known code requirements implemented.
- all local tests passed.
- all providers mock/fixture tested.
- providers live/sandbox tested.
- Railway deployed.
- owner lifecycle proven.
- 24–72 hour soak completed.
- multi-user load tested.
- payment test mode proven.
- demo broker execution proven.
- real execution proven.
- public production approved.

If any layer is missing, state it plainly and continue fixing everything that can be fixed from the available environment.

---

# 35. EXHAUSTIVE CODEBASE PROOF, LINE-LEVEL TRACEABILITY, FULL-SYSTEM INTEGRATION, LIVE CONNECTION TESTING, AND PRODUCTION EVIDENCE

This section is mandatory and supersedes any weaker interpretation of testing, completeness, or “production ready” elsewhere in this prompt.

## 35.1 Fundamental honesty rule

No engineer, test suite, code-coverage tool, or prompt can mathematically prove that a non-trivial production system will never fail under every possible future input, provider outage, network condition, broker behaviour, or infrastructure event.

Therefore:

- Do not claim impossible absolute perfection.
- Do not use “100% production ready” merely because tests pass.
- Do not equate code coverage with correctness.
- Do not equate mocked integrations with live integrations.
- Do not equate one successful signal with a proven system.
- Do not equate per-feature tests with a complete working product.

Instead, achieve the strongest possible evidence-backed standard by proving every owned production file, every reachable branch, every integration contract, every end-to-end flow, and the complete deployed system under normal, failure, recovery, restart, concurrency, and load conditions.

The release must fail whenever the required evidence is incomplete.

## 35.2 Every file and line must be accounted for

Create a **Repository Proof Manifest** covering every file in the project.

For each file record:

- Relative path.
- Purpose.
- Runtime role.
- Importers.
- Imported dependencies.
- Public functions/classes/constants.
- Environment variables read.
- Database tables/columns used.
- Redis keys/streams used.
- External services used.
- Scheduler ownership.
- Tests covering it.
- Line coverage.
- Branch coverage.
- Mutation score.
- Production reachability.
- Dead-code status.
- Security sensitivity.
- Current verification status.
- Known external blockers.

Classify files as:

- production_runtime
- migration
- test
- script
- deployment
- configuration
- documentation
- generated
- legacy
- experimental
- obsolete
- third_party/vendor

No production-owned file may remain unclassified.

No production-owned file may be excluded from verification merely because it is old, rarely called, feature-flagged, admin-only, broker-related, payment-related, or difficult to exercise.

Any file proven obsolete must be safely removed or moved into an explicitly isolated legacy/archive package, with import and migration compatibility checked.

## 35.3 Line-to-requirement traceability

Create a **Requirement-to-Code-to-Test Traceability Matrix**.

For every Universal Requirement Register item, map:

- requirement ID
- source
- implementing files
- implementing functions/classes
- database schema
- environment variables
- API/Telegram entry points
- test files
- test cases
- live verification step
- final evidence

For every production function/class, map back to at least one requirement, operational need, compatibility contract, or framework obligation.

Unmapped production code must be reviewed for:

- undocumented feature
- accidental dead code
- security risk
- duplication
- obsolete compatibility
- missing requirement
- missing test

## 35.4 Static verification of the entire repository

Run and fix, using the repository’s actual toolchain:

- Python compilation for every owned Python file.
- Import audit.
- circular-import audit.
- undefined-name audit.
- unused-import and unused-variable audit.
- unreachable-code audit.
- dead-code audit.
- type checking.
- linting.
- formatting checks.
- architecture-boundary checks.
- dependency-cycle checks.
- SQLAlchemy model/migration drift checks.
- environment-variable contract checks.
- duplicate route checks.
- duplicate Telegram command/callback registration checks.
- duplicate scheduler-job ID checks.
- duplicate strategy/provider registry keys.
- duplicate Redis key ownership.
- secret scanning.
- SAST/security scanning.
- dependency vulnerability audit.
- unsafe deserialisation audit.
- shell-script validation.
- Dockerfile/container configuration validation.
- YAML/TOML/JSON/env syntax validation.
- Git whitespace and accidental binary audit.

Use tools such as Ruff, Pyright/Mypy, Bandit, Semgrep, pip-audit, detect-secrets/gitleaks, Vulture, import-linter, ShellCheck, and Hadolint where compatible. Do not add a tool merely for appearance; configure and act on its findings.

Every suppression must include a precise justified comment and test.

## 35.5 Code coverage standard

Measure coverage from the complete automated suite, including unit, integration, contract, state-machine, and end-to-end tests.

Required targets:

### Critical modules

For:

- delivery
- lifecycle/outcomes
- risk
- execution
- payments
- authentication/authorisation
- database session/admission
- migrations
- Redis recovery
- Telegram webhook/callback routing
- provider validation
- resource governor
- kill switches
- consent
- idempotency

Require:

- 100% statement coverage where technically reachable.
- 100% branch coverage where technically reachable.
- explicit evidence for unreachable defensive branches.
- mutation testing on business-critical logic.

### Whole owned production codebase

Target:

- 100% file inclusion.
- at least 95% statement coverage.
- at least 90% branch coverage.
- no untested production entry point.
- no untested feature flag.
- no untested exception/recovery path in a critical module.

Do not lower targets by excluding difficult files.

Coverage exclusions are permitted only for:

- platform-impossible branches
- type-checking-only blocks
- explicit abstract interfaces
- externally generated code
- defensive process-exit lines that are separately contract-tested

Every exclusion must be listed in the final report.

Coverage alone is not proof. It must be combined with mutation, property, integration, and live tests.

## 35.6 Mutation testing

Run mutation testing on owned business logic.

At minimum mutate:

- direction comparisons.
- entry/SL/TP geometry.
- risk limits.
- lot rounding.
- tier gates.
- profile rules.
- cooldowns.
- expiry.
- outcome transitions.
- MFE/MAE.
- delivery idempotency.
- payment idempotency.
- provider freshness.
- market-session checks.
- resource thresholds.
- execution consent.
- kill switches.
- webhook authentication.
- score thresholds.

Required outcome:

- All high-risk surviving mutants fixed with stronger tests.
- Critical-module mutation score target: at least 90%.
- Whole tested business-logic mutation score target: at least 80%.
- Every surviving critical mutant documented and resolved before release.

## 35.7 Property-based and invariant testing

Use property-based testing for financial and lifecycle invariants.

Examples:

- Long signal: `SL < entry < TP1 <= TP2 <= TP3`.
- Short signal: `TP3 <= TP2 <= TP1 < entry < SL`.
- Position size is finite, positive, broker-step aligned, and within min/max.
- Risk amount never exceeds configured risk budget.
- Missing broker specifications block real execution.
- MFE and MAE never decrease incorrectly after additional valid observations.
- terminal states cannot return to active states.
- one user+signal pair cannot have two successful delivery proofs.
- duplicate webhook events cannot create duplicate payment entitlements.
- duplicate broker requests cannot place duplicate orders.
- Redis loss cannot delete durable PostgreSQL history.
- undelivered signals cannot enter live performance.
- expired signals cannot be sent.
- stale quotes cannot pass fail-closed delivery.
- profile filters cannot expand beyond the `all` profile’s valid union.
- provider candles remain ordered and satisfy OHLC geometry.
- generated timestamps never move backwards within one lifecycle.
- retry counts and queue leases remain bounded.

Use state-machine/property tools where appropriate.

## 35.8 Full dependency and relationship audit

Prove that every subsystem works correctly in relation to every other subsystem.

Audit and test:

- provider → normaliser
- normaliser → cache
- cache → strategy
- strategy → score
- score → risk
- risk → storage
- storage → audience selection
- audience → reservation
- reservation → Telegram
- Telegram → proof
- proof → active message
- active message → lifecycle
- lifecycle → outcome
- outcome → notification
- outcome → performance
- outcome → ML telemetry
- profile → strategy/timeframe/session eligibility
- tier → quota/features/delivery
- payment → entitlement
- entitlement → delivery
- broker link → consent → execution
- execution → reconciliation
- TradingView → validation → storage/delivery
- Redis → PostgreSQL recovery
- scheduler → job ownership
- resource governor → degradation
- admin/owner commands → audited actions
- environment variables → runtime configuration
- migrations → model definitions → repositories → reports

Detect and fix:

- orphan models.
- orphan migrations.
- unused columns.
- code reading nonexistent columns.
- environment variables never read.
- variables read but undocumented.
- routes hidden by mounts.
- callbacks with no handler.
- handlers with no registration.
- scheduler jobs with missing imports.
- strategies never registered.
- providers never reachable.
- feature flags that cannot enable a feature.
- duplicate canonical implementations.
- inconsistent enums.
- stale compatibility aliases.
- circular runtime ownership.

## 35.9 External connection testing

Do not stop at mocks.

Create a connection-certification suite that performs safe, read-only or sandbox calls against every configured external service.

### PostgreSQL and PgBouncer

Test:

- direct application connection through the actual Railway `DATABASE_URL`.
- `SELECT 1`.
- transaction begin/commit/rollback.
- concurrent session cap.
- PgBouncer transaction-pooling compatibility.
- migration head.
- schema/index existence.
- timeout.
- cancellation.
- reconnect.
- server restart recovery where feasible.

### RedisState

Test:

- ping.
- set/get/delete.
- expiration.
- NX/PX lock.
- Lua/script use if present.
- streams.
- consumer groups.
- pending recovery.
- pub/sub if used.
- pool cap.
- connection recovery.
- flush simulation followed by PostgreSQL rebuild.

### RedisDelivery

Test:

- webhook queue.
- delivery reservation.
- retry queue.
- dead-letter queue.
- consumer recovery.
- duplicate reservation prevention.
- queue-age metrics.
- restart recovery.

### Telegram

Using a dedicated test bot and test chat:

- `getMe`.
- `setWebhook`.
- `getWebhookInfo`.
- webhook secret/path validation.
- `sendMessage`.
- `editMessageText`.
- inline keyboard.
- callback query acknowledgement.
- Markdown/HTML formatting.
- long-message handling.
- RetryAfter simulation.
- blocked/deleted chat handling.
- duplicate update.
- restart with queued update.
- delivery-proof persistence.
- active-message update.
- outcome notification.

Do not send production test signals to ordinary users.

### Market-data providers

For every enabled/certified provider:

- resolve at least one valid symbol per supported asset class.
- request each supported production timeframe.
- request enough bars for strategy requirements.
- validate timestamps, ordering, geometry, volume, freshness, and provenance.
- test invalid symbol.
- test unsupported timeframe.
- test authentication failure where safe.
- test quota/rate-limit response.
- test timeout.
- test 5xx.
- test empty result.
- compare sample prices with another provider inside a configured tolerance.
- record live-versus-delayed status.
- record endpoint/version.

### Gemini

Test:

- valid request.
- structured response.
- timeout.
- 429/circuit.
- malformed response.
- deterministic fallback.
- cache/deduplication.
- budget enforcement.

### TradingView

Test a signed webhook through the real deployed route:

- valid alert.
- invalid signature.
- stale timestamp.
- duplicate idempotency key.
- invalid geometry.
- unsupported asset.
- queue persistence.
- database persistence.
- delivery eligibility.
- audit trail.

### Paystack

Use test mode:

- initialise.
- verify.
- signed webhook.
- duplicate webhook.
- incorrect amount.
- failed payment.
- refund test flow where supported.
- entitlement activation.
- receipt.
- reconciliation.

### MetaApi/MT5

Use demo only until separately approved:

- token validation.
- account status.
- connection.
- symbol discovery.
- live/demo quote.
- symbol specification.
- balance/equity.
- margin.
- open positions.
- safe demo order.
- idempotent duplicate request.
- modification.
- close.
- history.
- reconciliation.
- disconnect/reconnect.
- broker rejection.
- missing-symbol failure.
- no fallback lot.

If a provider or broker cannot be live-tested because of missing credentials, region, approval, or plan restrictions, mark it blocked and do not enable it in production.

## 35.10 Whole-system test environment

Create a reproducible full-stack test deployment containing:

- the complete SignalRankAI application.
- PostgreSQL.
- PgBouncer or a compatible transaction-pooling test setup.
- RedisState.
- RedisDelivery.
- dedicated Telegram test bot/chat.
- provider credentials or public endpoints.
- Paystack test mode.
- TradingView test secret.
- MetaApi demo account where supplied.
- test owner/admin/free/premium/VIP users.
- clean database fixture.
- deterministic clock controls where needed.
- structured log capture.
- metrics capture.

The full-stack environment must start from an empty database and empty Redis instances and be able to migrate, seed test identities, register the webhook, recover state, and execute all required system tests.

## 35.11 Full bot and system test — everything together

Do not rely only on isolated feature tests.

Build a **Complete System Orchestrator Test** that runs the real application stack and exercises the complete bot as one system.

The test must:

1. Start PostgreSQL/PgBouncer, both Redis instances, and the application.
2. Run migrations from an empty database.
3. Verify `/livez`, `/healthz`, and `/readyz`.
4. Register the Telegram webhook.
5. Create or initialise test users for all tiers:
   - free
   - premium
   - VIP
   - admin
   - owner
6. Complete onboarding for each canonical trader profile:
   - scalp
   - day
   - swing
   - position
   - all
7. Persist and reload every profile after restart.
8. Exercise every Telegram command and every inline button.
9. Fetch real or certified sandbox/public market data.
10. Fetch data concurrently across all enabled asset classes:
    - crypto spot
    - crypto perpetual/future
    - crypto options where available
    - forex
    - commodities
    - stocks/equities
    - indices
    - equity/futures derivatives where available
    - broker synthetic instruments where applicable
11. Validate every required timeframe.
12. Run every registered strategy against compatible data.
13. Verify rejected, delayed, suppressed, and accepted candidates.
14. Verify score, risk, deduplication, cooldown, profile, tier, market-session, freshness, and portfolio gates.
15. Store eligible signals.
16. Plan the full audience.
17. Acquire delivery reservations.
18. Send to the dedicated Telegram test chat/users.
19. Persist delivery proof.
20. Persist active messages.
21. Exercise callback buttons on delivered messages.
22. Move signals through the complete lifecycle using:
    - certified live data where naturally possible, and
    - deterministic replay through the real lifecycle engine for guaranteed TP/SL/missed/expiry scenarios.
23. Persist MFE, MAE, duration, R, provenance, and telemetry.
24. Send outcome notifications.
25. Generate user reports and owner/admin diagnostics.
26. Exercise paper trading.
27. Exercise TradingView signed alerts.
28. Exercise Paystack test mode.
29. Exercise MetaApi demo mode when credentials are available.
30. Restart the application mid-flow.
31. Verify recovery from PostgreSQL and both Redis instances.
32. Flush RedisState in the test environment and prove reconstruction.
33. Interrupt RedisDelivery and prove queued-delivery recovery.
34. Inject provider 429, timeout, stale, malformed, and outage conditions.
35. Inject Telegram RetryAfter and uncertain-send conditions.
36. Inject DB pool pressure.
37. Inject high memory/resource state.
38. Verify degradation and recovery.
39. Confirm no duplicate sends, outcomes, payments, or orders.
40. Confirm all queues drain or end in a known dead-letter state.
41. Confirm no unhandled exception.
42. Confirm no background task silently died.
43. Confirm no database session leaked.
44. Confirm no orphan lock or reservation remained.
45. Confirm no active durable signal was lost.
46. Confirm performance evidence remained provenance-separated.
47. Produce one machine-readable test report linking every step to logs, rows, keys, message IDs, and outcome records.

This test must run the full bot and system together, not a collection of unrelated test functions.

## 35.12 All-asset end-to-end matrix

Run full end-to-end scenarios for each supported asset class.

Each scenario must prove:

- symbol discovery/mapping.
- market session.
- provider selection.
- OHLC fetch.
- optional WebSocket/tick route if enabled.
- normalisation.
- required bars.
- strategy compatibility.
- candidate generation or documented legitimate rejection.
- score.
- risk.
- storage.
- delivery.
- lifecycle.
- outcome.
- reporting.
- telemetry.
- restart recovery.

At minimum include representative symbols such as:

- crypto spot: BTC/USD or BTC/USDT.
- crypto perpetual: a verified BTC perpetual symbol.
- crypto option: a verified Deribit/Bybit option instrument when supported.
- forex: EUR/USD.
- commodity: gold/XAU or a provider-supported gold future.
- stock: a liquid US equity.
- index: S&P 500 or a provider-supported equivalent.
- derivative: a supported future or option.
- synthetic broker asset: only when the linked demo broker exposes it.

Do not hard-code one provider’s symbols as canonical platform symbols.

A legitimate no-signal result is acceptable only when the entire data and decision flow succeeds and the rejection reason is valid and persisted.

## 35.13 Cross-product test matrix

Generate and execute a risk-based pairwise/full matrix across:

- asset class
- market type
- timeframe
- strategy
- trader profile
- tier
- direction
- market session
- provider
- delivery mode
- outcome
- resource state
- failure mode

Use pairwise generation for the broad combinatorial surface and full enumeration for critical combinations.

Critical full-enumeration combinations include:

- all tiers × all profiles.
- all profiles × allowed timeframes.
- all asset classes × market session open/closed.
- advisory/paper/demo/real-gated execution modes.
- every lifecycle terminal state.
- every payment state.
- every delivery state.
- every provider circuit state.

## 35.14 Chaos, fault, and recovery testing

Test the deployed system under:

- PostgreSQL unavailable.
- PgBouncer timeout.
- DB pool exhaustion.
- transaction rollback.
- one Redis unavailable.
- both Redis unavailable.
- Redis flush.
- stale Redis cache.
- duplicate Redis entry.
- Telegram timeout.
- Telegram RetryAfter.
- Telegram success response followed by DB failure.
- DB proof persisted followed by process crash.
- provider 429.
- provider 401/403.
- provider 5xx.
- malformed candle.
- out-of-order candle.
- duplicate candle.
- stale quote.
- cross-provider disagreement.
- WebSocket disconnect.
- WebSocket message storm.
- network latency.
- Gemini outage.
- Paystack replay.
- TradingView replay.
- MetaApi disconnect.
- broker rejection.
- process SIGTERM.
- process crash.
- Railway redeploy.
- memory pressure.
- CPU pressure.
- clock skew within safe simulated bounds.

For each fault verify:

- correct categorisation.
- bounded retries.
- no busy loop.
- no duplicate action.
- no loss of durable truth.
- correct degradation.
- correct user message where applicable.
- correct alert.
- automatic recovery where safe.
- manual runbook where automatic recovery is unsafe.

## 35.15 Load and latency testing

Test the one-service Railway Hobby target with realistic constraints.

Measure:

- webhook ACK p50/p95/p99.
- callback ACK p50/p95/p99.
- provider fetch latency.
- cycle duration.
- candidate-to-send latency.
- reservation latency.
- Telegram send latency.
- proof-persistence latency.
- lifecycle update latency.
- DB admission wait.
- Redis latency.
- event-loop lag.
- memory.
- CPU.
- queue depth.
- retry rate.
- error rate.

Scenarios:

- 1 user.
- 10 users.
- 100 users.
- 1,000 users in simulated fan-out.
- 100,000-user audience-planning simulation.
- 1,000 callback updates.
- rejection burst.
- provider outage during fan-out.
- restart during lifecycle tracking.

Set release thresholds based on product timeframes and Railway capacity. Do not pretend the Hobby service can provide high-frequency exchange co-location latency.

## 35.16 Production-like clean-room deployment test

Prove that a new engineer can deploy the system using only the repository and documentation.

From a clean environment:

- clone/extract repository.
- create PostgreSQL.
- create both Redis instances.
- configure variables.
- build image.
- start service.
- run migration.
- pass health checks.
- register webhook.
- run smoke test.
- run complete system orchestrator test.
- run owner lifecycle proof.

No undocumented manual database edit, file copy, hidden secret, local machine dependency, or stale cache may be required.

## 35.17 Railway staging proof

After local/full-stack success, deploy to a Railway staging environment using the same one-service architecture.

Required staging evidence:

- successful build.
- successful migration.
- one Uvicorn worker.
- no duplicate task ownership.
- `/livez`, `/healthz`, `/readyz`.
- PostgreSQL/PgBouncer.
- RedisState.
- RedisDelivery.
- Telegram test bot.
- provider live/public/sandbox connections.
- complete all-asset test matrix for enabled providers.
- complete bot/system test.
- restart recovery.
- redeploy recovery.
- resource metrics.
- 24–72 hour soak.
- no recurring critical/high defects.

The final production profile may enable only providers and capabilities that passed the required staging certification.

## 35.18 Canary and production release proof

Production rollout must be staged:

1. owner-only.
2. internal test users.
3. limited free users.
4. limited premium/VIP test users.
5. Paystack test/controlled paid beta.
6. broader advisory release.
7. demo broker pilot.
8. separately approved real-execution pilot.

At each stage:

- define entry criteria.
- define exit criteria.
- define rollback.
- monitor errors, latency, resource use, delivery, outcomes, and complaints.
- stop expansion on any release-blocking pattern.

## 35.19 Long-running soak

Run a minimum 24-hour soak and preferably 72 hours for the intended owner-beta/full-advisory profile.

During soak verify:

- no memory leak.
- no connection leak.
- no task loss.
- no growing queue.
- no duplicate scheduler job.
- no stale active signal.
- no provider restart thrashing.
- no repeated Gemini hammering.
- no recurring DB starvation.
- no undelivered exposure contamination.
- no outcome contamination.
- no Telegram callback failure.
- no missed required notification.
- no unexpected process restart.
- correct restart recovery if Railway restarts the service.

Capture metrics over time, not only final status.

## 35.20 Test-result integrity

Do not hide failures through:

- blanket `try/except`.
- test deletion.
- broad skip.
- xfail without issue and reason.
- reducing assertions.
- replacing real tests with booleans.
- disabling features.
- increasing timeouts without diagnosis.
- clearing data that exposes failures.
- lowering risk or quality thresholds.
- mocking the unit under test.
- accepting empty provider responses as success.

Every skip/xfail must include:

- exact reason.
- external blocker.
- owner.
- follow-up action.
- production impact.

## 35.21 Automatic gap discovery from test failures

When any full-system test breaks:

1. preserve logs, trace IDs, rows, Redis entries, request/response metadata, and environment.
2. identify root cause.
3. search for the same pattern across the repository.
4. repair the canonical implementation.
5. add the smallest focused regression test.
6. rerun the focused test.
7. rerun affected integration tests.
8. rerun the complete system orchestrator.
9. rerun static, coverage, and mutation checks.
10. update requirement and gap registers.

Do not patch only the symptom.

## 35.22 Mandatory release artefacts

In addition to all previous deliverables, produce:

- Repository Proof Manifest.
- Requirement-to-Code-to-Test Traceability Matrix.
- Complete coverage HTML/XML/JSON reports.
- Branch-coverage report.
- Mutation-testing report.
- Static-analysis report.
- Security/dependency report.
- Provider live-certification evidence.
- External connection test report.
- Complete System Orchestrator report.
- All-Asset End-to-End Matrix.
- Cross-Product Matrix results.
- Chaos/recovery report.
- Load/latency report.
- clean-room deployment report.
- Railway staging report.
- soak report.
- unresolved-skip register.
- exact failed/blocked external integrations.
- final checksums.

## 35.23 Final release gate

The agent must not declare the project complete while any of the following remains:

- unclassified production file.
- untested production entry point.
- undefined callback.
- registered command without a working flow.
- provider enabled without live/sandbox/public certification.
- profile that does not alter real engine/delivery behaviour.
- tier inconsistently enforced.
- missing database migration.
- model/migration drift.
- Redis recovery not proven.
- delivery proof not proven.
- lifecycle not proven.
- all-asset E2E scenario not proven for an enabled asset class.
- payment replay not proven safe.
- demo broker execution not reconciled.
- critical surviving mutation.
- unexplained coverage exclusion.
- critical/high static or security finding.
- full-system orchestrator failure.
- Railway staging health failure.
- recurring soak defect.
- release documentation mismatch.
- missing rollback procedure.

## 35.24 Exact final verdict language

The final verdict must use an evidence table and may only mark a row passed when its evidence exists:

- REPOSITORY_STATIC_VERIFIED
- CRITICAL_CODE_100_PERCENT_COVERED
- MUTATION_TARGETS_MET
- ALL_UNIT_TESTS_PASSED
- ALL_INTEGRATION_TESTS_PASSED
- COMPLETE_SYSTEM_TEST_PASSED
- ALL_ENABLED_PROVIDERS_CERTIFIED
- ALL_ENABLED_ASSET_CLASSES_E2E_PASSED
- ALL_PROFILES_E2E_PASSED
- ALL_TIERS_E2E_PASSED
- TELEGRAM_FULL_FLOW_PASSED
- REDIS_RECOVERY_PASSED
- PGBOUNCER_COMPATIBILITY_PASSED
- TRADINGVIEW_FLOW_PASSED
- PAYSTACK_TEST_FLOW_PASSED
- METAAPI_DEMO_FLOW_PASSED
- CHAOS_RECOVERY_PASSED
- LOAD_TARGETS_PASSED
- CLEAN_ROOM_DEPLOYMENT_PASSED
- RAILWAY_STAGING_PASSED
- OWNER_LIFECYCLE_PROOF_PASSED
- SOAK_PASSED
- LIMITED_PUBLIC_RELEASE_APPROVED
- PAID_BETA_APPROVED
- REAL_EXECUTION_APPROVED

A failed, blocked, skipped, or unavailable row must never be shown as passed.

---

# 36. NON-STOP COMPLETION CONTRACT, PERMISSION ESCALATION, BLOCKER MANAGEMENT, AND DEFENSIBLE SIGN-OFF

This section is mandatory and overrides any weaker instruction that would allow the implementation agent to stop after analysis, planning, partial fixes, isolated tests, or a preliminary deployment.

## 36.1 Core execution commitment

The implementation agent must continue working until every action that can be completed with the available repository, tools, infrastructure, credentials, permissions, and information has been completed and verified.

The agent must not voluntarily stop because:

- the repository is large;
- the task takes many passes;
- the test suite is slow;
- a failure is difficult;
- multiple subsystems are affected;
- an initial fix appears successful;
- one provider works;
- one asset class works;
- one Telegram signal is delivered;
- unit tests pass;
- static analysis passes;
- a staging deployment starts;
- a report has been written;
- a checklist has been produced;
- context is lengthy;
- the first implementation attempt fails;
- a new hidden defect is discovered;
- a dependency needs to be installed;
- a migration needs to be written;
- a test needs to be redesigned;
- a live integration needs a safe credential or sandbox account.

The agent must keep investigating, implementing, testing, repairing, retesting, documenting, and packaging until the Definition of Done and final release gates are satisfied or a genuine external blocker remains that only the project owner or third party can resolve.

## 36.2 No plan-only or advice-only completion

The following do not count as task completion:

- architecture recommendations without code;
- pseudocode;
- partial snippets;
- TODO lists;
- “next steps” without executing them;
- a defect report without repairs;
- a patch without tests;
- tests without integration;
- integration without live/sandbox connection proof;
- mocked provider tests without provider certification;
- a deployment guide without a deployable repository;
- a successful deployment without full-system evidence;
- a successful owner signal without lifecycle and restart proof;
- an environment file that does not match code;
- documentation that describes features not reachable in the application.

The agent must directly modify the supplied codebase, create migrations, create or update tests, run those tests, fix failures, run the complete system test, prepare the Railway deployment, and return the full repository and evidence artefacts.

## 36.3 Autonomous progress within granted authority

Within the permissions already granted, the agent should act without repeatedly asking for confirmation.

The agent may autonomously perform reversible development actions such as:

- inspect all files;
- create a Git baseline;
- create branches or local commits;
- edit code;
- add tests;
- add migrations;
- update environment examples;
- run local databases and Redis containers;
- run mock/sandbox services;
- install approved development dependencies;
- run linters, type checkers, security scanners, coverage, mutation and load tests;
- create fixtures;
- create test users in isolated test databases;
- create local Docker/Compose environments;
- package release artefacts;
- generate reports and checksums;
- create safe Railway configuration files;
- retry failed non-destructive tests;
- continue other work while one task is blocked.

Do not ask for permission for routine, reversible repository work.

## 36.4 Actions requiring explicit permission

Request explicit permission before:

- deploying to a real production environment;
- changing production Railway variables;
- running irreversible or destructive production migrations;
- deleting or rewriting production data;
- rotating real secrets;
- enabling public payments;
- initiating real refunds or payouts;
- enabling real broker execution;
- placing a real-money trade;
- modifying real broker positions;
- broadcasting to real users;
- changing subscription prices or billing policy;
- enabling copy trading for real accounts;
- accessing accounts or services not already authorised;
- incurring paid provider charges beyond an agreed limit;
- changing legal, compliance, privacy, or financial policies;
- performing an action that could materially affect users, money, or production availability.

When permission is required, the agent must ask clearly and precisely, then continue every unrelated unblocked task instead of stopping the entire project.

## 36.5 Consolidated permission and information request protocol

Do not interrupt the owner with many small questions.

Maintain a **Permission and Information Queue** and batch requests where possible.

Each request must state:

- Request ID.
- Exact permission, credential, access, or decision needed.
- Why it is needed.
- The exact subsystem blocked.
- Whether the request is required or optional.
- Security sensitivity.
- The safest way for the owner to provide it.
- What the agent will test after receiving it.
- What work continues without it.
- The deadline or project phase where it becomes blocking.
- A safe default when one exists.
- Consequence of not providing it.

Example categories:

### Repository and infrastructure access

- Current repository archive or GitHub access.
- Railway project access.
- Railway staging environment access.
- PostgreSQL staging credentials.
- RedisState staging credentials.
- RedisDelivery staging credentials.
- deployment logs.
- database backup confirmation.

### Telegram

- Dedicated Telegram test bot token.
- Dedicated test chat/group.
- test user Telegram IDs for free, premium, VIP, admin and owner.
- permission to register the staging webhook.
- permission to send only to designated test chats.

### Providers

- Alpha Vantage key.
- Twelve Data key.
- EODHD key.
- Marketstack key.
- Finnhub key.
- FMP key.
- Tiingo key.
- Polygon key.
- Alpaca sandbox credentials.
- OANDA practice credentials.
- Tradier sandbox credentials.
- other selected provider keys.
- provider account approval.
- regional access information.

### AI

- Gemini API key.
- approved daily/token budget.
- permission to run bounded live API certification calls.

### TradingView

- staging webhook secret.
- permitted test alert format.
- permission to send test alerts to the staging route.

### Payments

- Paystack test secret/public keys.
- test webhook secret/configuration.
- permission to run test transactions and test refunds.
- final tier prices and billing periods.

### Brokers

- MetaApi token.
- MetaApi demo account ID.
- permission to place, modify and close demo-only orders.
- broker server/account metadata.
- explicit confirmation that live execution remains disabled.

### Security and ownership

- encryption key placement confirmation.
- owner/admin Telegram IDs.
- final data-retention policy.
- final privacy/contact/support details.
- legal/compliance sign-off where applicable.

Do not ask the owner to paste secrets into chat when a safer mechanism exists. Prefer instructions such as:

- add the secret directly to Railway Variables;
- seal it;
- provide only the environment-variable name and confirmation that it has been set;
- use a dedicated staging/test account;
- rotate any secret accidentally exposed.

## 36.6 Missing information must not cause assumption

When a required business rule or credential is missing:

- Do not invent it.
- Do not choose a production price, subscription period, risk threshold, legal statement, broker policy, or user entitlement without evidence.
- Preserve the currently implemented safe default when appropriate.
- Mark the exact decision as unresolved.
- Request the missing information.
- Continue every unaffected implementation and test.
- Build validation so the application fails clearly when the unresolved value is required.
- Do not label the affected feature complete.

## 36.7 Blocker classification

Maintain an **External Blocker Register**.

Classify each blocker as:

- OWNER_PERMISSION_REQUIRED
- OWNER_INFORMATION_REQUIRED
- SECRET_REQUIRED
- PROVIDER_CREDENTIAL_REQUIRED
- PROVIDER_REGION_BLOCKED
- PROVIDER_ACCOUNT_APPROVAL_REQUIRED
- PAID_PLAN_REQUIRED
- BROKER_DEMO_ACCOUNT_REQUIRED
- LEGAL_OR_COMPLIANCE_DECISION_REQUIRED
- PRODUCTION_ACCESS_REQUIRED
- THIRD_PARTY_OUTAGE
- THIRD_PARTY_DEPRECATION
- TOOL_OR_ENVIRONMENT_LIMITATION
- IRREVERSIBLE_ACTION_APPROVAL_REQUIRED

For each blocker include:

- exact affected requirement;
- all completed preparatory work;
- automated tests already passing;
- live test still required;
- exact owner action;
- exact command or UI step after unblocking;
- risk of proceeding without it;
- safe fallback;
- whether the release can proceed without the feature disabled.

A blocker is not a reason to abandon unrelated work.

## 36.8 Parallel progress rule

When one task is blocked, continue in parallel on:

- code audit;
- tests;
- documentation;
- provider adapters not requiring credentials;
- fixtures;
- mock contracts;
- security;
- migrations;
- local integration;
- Docker environment;
- Railway configuration;
- performance;
- recovery;
- Telegram flows;
- ML telemetry;
- reports;
- packaging.

The agent should return to the blocked task immediately after the owner supplies the required permission or detail.

## 36.9 Resumable checkpoints

Because the project may exceed one execution session, maintain durable checkpoints.

At the end of every implementation pass, write a machine-readable checkpoint containing:

- timestamp;
- repository commit/hash;
- current branch;
- files changed;
- migrations added;
- tests run;
- exact results;
- coverage;
- mutation score;
- live integrations tested;
- current blockers;
- next executable task;
- commands required to resume;
- artefact checksums.

Use a persistent file such as:

```text
docs/WORK_COMPLETION_CHECKPOINT.json
docs/WORK_COMPLETION_CHECKPOINT.md
```

On every resumed session:

1. Read the checkpoint.
2. Verify repository hash.
3. Re-run a fast integrity check.
4. Continue from the exact next task.
5. Do not repeat completed work unnecessarily.
6. Do not forget unresolved blockers.

## 36.10 Failure persistence and retry discipline

A failure must trigger investigation, not abandonment.

For every failure:

1. Capture the full error.
2. Preserve trace IDs and relevant logs.
3. Reproduce deterministically where possible.
4. Identify root cause.
5. Search for the same pattern elsewhere.
6. Fix the canonical implementation.
7. Add a focused regression test.
8. Re-run the focused test.
9. Re-run affected integration tests.
10. Re-run the Complete System Orchestrator.
11. Update the gap and requirement registers.
12. Continue until the failure is resolved or externally blocked.

Do not endlessly retry an unchanged failing operation. Retries must be bounded and follow diagnosis.

## 36.11 Completion defence package

The agent must be able to defend every completion claim with evidence.

Create a **Completion Defence Package** containing:

- Universal Requirement Register.
- Cross-Chat Decision Ledger.
- Repository Proof Manifest.
- Requirement-to-Code-to-Test Traceability Matrix.
- Feature Coverage Matrix.
- Provider Certification Matrix.
- Asset-Class E2E Matrix.
- Trader Profile E2E Matrix.
- Tier E2E Matrix.
- Command/Callback/Button Matrix.
- Strategy Coverage Matrix.
- Environment Variable Contract.
- migration report.
- schema report.
- static-analysis report.
- security report.
- dependency report.
- coverage reports.
- mutation report.
- property-test report.
- integration report.
- external-connection report.
- Complete System Orchestrator report.
- chaos/recovery report.
- load/latency report.
- clean-room deployment report.
- Railway staging report.
- lifecycle evidence.
- soak report.
- blocker register.
- rollback runbook.
- final repository ZIP.
- Git patch.
- SHA-256 checksums.

Every report must reference:

- command executed;
- environment;
- date/time;
- commit hash;
- result;
- logs or artefacts;
- unresolved limitation.

## 36.12 Demonstrable completion

The final release must be demonstrable.

Provide one command or documented sequence that allows an authorised reviewer to:

1. Start the full test stack.
2. Run migrations.
3. Run static verification.
4. Run all automated tests.
5. Run coverage.
6. Run mutation tests.
7. run provider certification.
8. run external connection tests.
9. run the Complete System Orchestrator.
10. run all-asset E2E tests.
11. run chaos/recovery tests.
12. run load tests.
13. generate the Completion Defence Package.

Provide a shorter pre-deploy release command and a deeper full-certification command.

Example intent:

```bash
python scripts/verify_release.py --profile railway-hobby --full
python scripts/certify_external_integrations.py --staging
python scripts/run_complete_system_test.py --all-assets
```

Use the repository’s actual command names and implementation.

## 36.13 Owner-review demonstration

Prepare a controlled owner demonstration script that proves:

- bot starts;
- webhook works;
- commands work;
- callbacks work;
- profiles persist;
- tiers enforce correctly;
- each enabled asset class fetches data;
- provider provenance is visible;
- one accepted signal delivers;
- one rejected candidate is tracked;
- one missed entry resolves;
- one TP resolves;
- one SL resolves;
- MFE/MAE telemetry persists;
- paper trading works;
- TradingView test works;
- Paystack test mode works;
- MetaApi demo works when credentials exist;
- restart recovery works;
- Redis recovery works;
- health and diagnostics work;
- reports distinguish evidence classes.

The demonstration must use dedicated staging/test users and must not send test activity to ordinary production users.

## 36.14 No premature “done” statement

The agent may say “complete” only when:

- every known code-verifiable requirement is implemented;
- all mandatory local tests pass;
- the full-system orchestrator passes;
- every enabled provider is certified;
- every enabled asset class passes E2E;
- every trader profile and tier passes E2E;
- security and mutation gates pass;
- clean-room deployment passes;
- Railway staging passes;
- same-signal lifecycle proof passes;
- the required soak passes;
- no unresolved critical/high defect remains;
- all external blockers are either resolved or the blocked feature is explicitly disabled and excluded from the claimed release scope;
- the Completion Defence Package is complete.

Otherwise, the exact status must be:

- WORK_IN_PROGRESS
- CODE_COMPLETE_BUT_LIVE_PROOF_PENDING
- BLOCKED_BY_OWNER_PERMISSION
- BLOCKED_BY_MISSING_CREDENTIAL
- BLOCKED_BY_THIRD_PARTY
- STAGING_VERIFIED
- OWNER_BETA_VERIFIED
- LIMITED_PUBLIC_VERIFIED
- PAID_BETA_VERIFIED
- REAL_EXECUTION_VERIFIED

Do not collapse these statuses into one broad “production ready” statement.

## 36.15 Final owner request

At the earliest useful point, generate one consolidated owner request listing every permission, credential, business decision, staging account, and external access required to complete all live certification.

Do not wait until the end to reveal that essential credentials were missing.

After the owner provides them:

- validate them safely;
- never print them;
- run the blocked certification tests;
- fix any newly exposed defects;
- rerun the entire affected system flow;
- update all evidence;
- continue until all release gates are met.

## 36.16 Maximum-effort completion rule

Use all available capabilities, tools, test frameworks, official documentation, repository history, logs, connected services, and safe staging infrastructure required to finish the project.

Do not knowingly leave:

- a partially implemented feature;
- a broken button;
- an untested command;
- an unregistered handler;
- an unverified provider;
- a missing migration;
- a stale environment variable;
- a dead scheduler job;
- an unsafe fallback;
- a hidden exception;
- an unexplained test skip;
- an unproven recovery path;
- an incomplete deployment instruction;
- a documentation/code contradiction;
- an unresolved critical or high defect.

When a feature cannot be completed because of a genuine external restriction, complete every internal component, test it with mocks/contracts, document the exact blocker, keep it disabled, and request what is necessary to finish live proof.

The project is finished only when the agent can defend the claimed release scope with reproducible evidence, not assumptions.


---

# SIGNALRANKAI V4 ADDENDUM
## Historical Requirements Reconstruction, Gap-Closure Mandate, Canonical Product Specification, and Final Completion Contract

This addendum is designed to be appended to:

`SignalRankAI_Master_Completion_Prompt_v4_Nonstop_Defensible_Completion.md`

It is intentionally self-contained. The implementation agent receiving it may have no access to the prior SignalRankAI conversations. Therefore, every requirement below must be treated as part of the project specification and reconciled against the latest repository, logs, migrations, tests, documentation, and deployed behaviour.

Where this addendum conflicts with an older implementation or document, use this precedence:

1. The latest explicit user decision recorded in this addendum.
2. The latest repository and database migration truth.
3. The latest Railway logs and live behaviour.
4. The latest dated project report.
5. Older compatibility behaviour.
6. General assumptions.

Do not invent missing prices, secrets, legal text, provider entitlements, broker permissions, or production performance. Ask for them through the consolidated Permission and Information Queue while continuing every unblocked task.

---

# 37. HISTORICAL PROJECT IDENTITY AND PRIMARY GOAL

## 37.1 Product identity

The project is named:

- `SignalRankAI`
- `SignalRankAI1` in some repository snapshots

It is a Telegram-first, multi-user, multi-asset trading-intelligence ecosystem, not merely a signal-alert bot.

The intended end state includes:

- Market-data ingestion.
- Dynamic asset discovery.
- Multi-provider OHLC and live-price routing.
- Multi-timeframe analysis.
- Modular trading strategies.
- Regime and market-session intelligence.
- Signal scoring and ranking.
- Risk and portfolio controls.
- Tiered Telegram delivery.
- Delivery proof.
- Signal lifecycle tracking.
- TP, SL, missed-entry and expiry outcomes.
- Paper trading.
- Shadow tracking.
- Backtesting and walk-forward evaluation.
- AI and ML review.
- News and macro intelligence.
- Optional on-chain intelligence.
- User profiles and preferences.
- Portfolio and performance reporting.
- Subscriptions, referrals, receipts, refunds and support.
- TradingView alert ingestion.
- MT5/MetaApi broker integration.
- Optional copy trading and auto-execution, gated by tier, consent and independent safety release.
- Admin and owner operational controls.
- Railway deployment tooling.
- Full observability, governance and production evidence.

The platform must remain Telegram-first for the current release. A dedicated mobile/web application may be added later, but it must not delay completion of the Telegram product.

## 37.2 Primary success criteria

The platform must:

- Generate fewer but higher-quality signals rather than lower thresholds merely to produce activity.
- Support many users without cross-user data access or preference leakage.
- Keep generated, stored, delivered, paper, shadow, backtest, walk-forward, demo-executed and live-executed evidence separate.
- Never claim a signal was delivered unless Telegram success and delivery proof exist.
- Never claim a win rate or minimum profitability without statistically valid evidence.
- Never guarantee the previously discussed aspirational 60% win rate. Treat it as a research target, not a product promise or release criterion.
- Continue operating safely when optional providers, Gemini, WebSockets or analytics are unavailable.
- Fail closed when delivery freshness, broker state, execution risk, payment authenticity or evidence truth is uncertain.
- Be deployable as a safe Railway Hobby monolith before being split into multiple runtime services.

---

# 38. CANONICAL USERS, ROLES, TIERS AND ENTITLEMENTS

## 38.1 Canonical roles and tiers

The canonical values are:

- `free`
- `premium`
- `vip`
- `admin`
- `owner`

Compatibility aliases may exist, but all access control must resolve to these canonical values.

## 38.2 Free tier

Expected capabilities include:

- Onboarding and terms acceptance.
- Basic profile configuration.
- Basic advisory signals.
- Signal proof and outcome views.
- Paper-trading tools.
- Support and issue reporting.
- Referrals.
- Public-test status.
- Basic market and provider status where permitted.

Historical delivery policy:

- Three random eligible signals per day.
- Different free users may receive different eligible signals from the global pool.
- One additional signal per eligible extra-signal purchase.
- The additional signal should be the highest-scoring eligible ongoing signal not previously delivered to the user.

This policy must be verified against the latest tier configuration before launch.

## 38.3 Premium tier

Expected capabilities include:

- More signals.
- Performance and history.
- Portfolio.
- Risk views.
- Filters.
- Reports.
- Notifications.
- Broker-status surfaces.
- Advanced analysis.
- Referrals.
- Profile controls.
- Optional broker linking when separately enabled.

Historical delivery policy:

- Ten eligible signals per day.
- A historical score band around 55–80 was discussed.
- Do not hard-code this band without verifying the latest central tier policy.

## 38.4 VIP tier

Expected capabilities include:

- Highest advisory quality.
- Highest signal volume.
- Elite/early/report tools.
- More configurable risk and webhook settings.
- Simulation tools.
- Optional execution features after independent approval.

Historical delivery policy:

- Thirty signals per day.
- Historical score threshold around 72 or above.
- Verify against the current tier policy.

## 38.5 Admin and owner

Admin capabilities include:

- User and subscription support.
- Diagnostics.
- Broadcasts.
- Signal/provider/payment lookup.
- Receipts and refunds lookup.
- System reports.
- Controlled subscription corrections.
- QA and audit commands.

Owner capabilities include:

- Full diagnostics.
- Development pause/resume.
- Controlled force/correction tools.
- User/revenue/version/provider controls.
- Broadcasts.
- Release guard and operational insight.

All privileged actions must be:

- Role-gated.
- Auditable.
- Idempotent where applicable.
- Explicit.
- Unable to alter historical evidence silently.
- Protected against callback tampering and IDOR.

## 38.6 Subscription periods and prices

Weekly and monthly subscription periods have been discussed historically, but exact current prices must be recovered from:

- The current code/configuration.
- The latest business-policy document.
- The latest explicit owner decision.

Do not invent subscription prices. If no canonical values exist, keep public payment activation disabled and request the decision.

---

# 39. CANONICAL TRADER PROFILES AND PERSONALISATION

## 39.1 Profiles

The canonical trader profiles are:

- `scalp`
- `day`
- `swing`
- `position`
- `all`

They must work for:

- New users during onboarding.
- Existing users.
- Telegram menus and callbacks.
- API representation.
- Database persistence.
- Engine selection.
- Signal delivery.
- Resends.
- Reports.
- Paper trading.
- Broker execution eligibility.
- Restart recovery.

## 39.2 Profile behaviour

### Scalp

- Primarily short timeframes.
- Strictest quote freshness.
- Strictest spread, liquidity and latency filters.
- Shortest expiry.
- Rapid outcome checks.
- No delayed data.
- No queue-delayed delivery when the opportunity is no longer valid.
- Strong market-session and microstructure requirements.

### Day

- Intraday timeframes.
- Signals should normally be able to reach an outcome within one day.
- Session-aware expiry.
- Clear overnight exposure policy.
- Strong time-to-target scoring.
- Market-open and session-transition awareness.

### Swing

- Higher-timeframe alignment.
- Longer expiry.
- Lower sensitivity to short-term noise.
- Weekend and holiday handling by asset class.
- Fresh final delivery quote remains mandatory.

### Position

- Higher-timeframe trend and macro context.
- Longest governed expiry.
- Funding, rollover, corporate events and macro risk where applicable.
- Requires adequate historical depth.
- Must not rely on an intraday-only feed for long-horizon evidence.

### All

- Valid union of supported profiles.
- No duplicate delivery.
- No bypass of risk, tier, cooldown, freshness or portfolio controls.

## 39.3 User preferences

Persist and apply:

- Trading style.
- Risk profile.
- Preferred asset classes.
- Specific assets.
- Strategies.
- Timeframes.
- Market sessions.
- Notification settings.
- Early-exit notifications.
- Outcome notifications.
- Language.
- Timezone.
- Delivery mode.
- Execution mode.
- Lot/risk guidance.
- Broker settings.
- Privacy and referral preferences.

Users must be able to update preferences. Existing users must be migrated safely.

## 39.4 Timezone and market-hours experience

The bot must:

- Store the user’s timezone.
- Tell users when a market is closed.
- Show expected reopen time in the user’s timezone.
- Show which session is active or monitored.
- Respect daylight-saving time.
- Respect exchange holidays and early closes.
- Keep crypto 24/7 logic separate.
- Treat broker synthetic indices according to broker schedules.

---

# 40. ASSET CLASSES, MARKETS AND TIMEFRAMES

## 40.1 Required asset coverage

The architecture must support:

- Crypto spot.
- Crypto perpetuals.
- Crypto futures.
- Crypto options when provider support exists.
- Forex.
- Commodities.
- Stocks/equities.
- Indices.
- Futures.
- Equity options where data exists.
- Other derivatives where correctly classified.
- Broker synthetic instruments where a linked broker supports them.
- Macro, yields and volatility as analysis-only unless explicitly made tradable.

Do not classify derivatives as spot because a symbol ends in USDT.

## 40.2 Canonical product timeframes

Required signal timeframes:

- `5m`
- `15m`
- `1h`
- `4h`
- `1d`

Internal provider support may include `1m` and broader horizons, but every product-facing timeframe must be provider-capability aware.

## 40.3 Historical cooldown defaults

Reconcile these historical defaults with the latest policy:

- `15m`: 10 minutes.
- `1h`: 20 minutes.
- `4h`: 90 minutes.
- `1d`: 6 hours.

## 40.4 Per-user repeat protection

Historical owner requirement:

- After a signal for an asset is successfully delivered to a user, do not deliver another signal for that same asset to that user for four hours by default.
- The lock is based on delivery proof.
- Stored-but-undelivered rows must not trigger it.
- Active-asset locking and full fingerprint deduplication still apply.
- Make the duration configurable.
- Test expiry, restart recovery and Redis loss.

---

# 41. PROVIDER ECOSYSTEM AND DATA-QUALITY CONTRACT

## 41.1 Public/free crypto and derivatives providers

Research, implement, classify and certify as applicable:

- Coinbase Advanced Trade REST/WebSocket.
- OKX public REST/WebSocket.
- Kraken public REST/WebSocket.
- Binance spot.
- Binance futures.
- Bybit V5 spot.
- Bybit linear/inverse futures.
- Bybit options.
- Deribit perpetuals/futures/options.
- KuCoin.
- CoinGecko.
- CryptoCompare.
- CCXT-compatible public feeds where operationally appropriate.

## 41.2 Multi-asset and keyed providers

Research, implement, classify and certify as applicable:

- Alpha Vantage.
- Twelve Data.
- EODHD.
- Marketstack.
- Finnhub.
- Financial Modeling Prep.
- Tiingo.
- Polygon.
- Alpaca.
- Tradier sandbox.
- OANDA practice.
- Nasdaq Data Link.
- Stooq.
- yfinance/Yahoo.
- Dukascopy historical feeds.
- MT5/MetaApi broker data.
- Deriv broker instruments.

## 41.3 Provider roles

Classify each provider as one or more:

- Primary real-time.
- Secondary real-time.
- Historical.
- Discovery.
- Analysis-only.
- Broker-validation-only.
- Sandbox-only.
- Regional fallback.
- Disabled.
- Unsuitable for production.

Not every provider should be called in every cycle.

## 41.4 Required provider capabilities

Each enabled provider requires:

- Current official API research.
- Supported classes and market types.
- Supported timeframes.
- Symbol mapping.
- Authentication/signing.
- Rate-limit and quota accounting.
- Bounded concurrency.
- Request coalescing.
- Timeouts.
- Backoff.
- Circuit breaker.
- Half-open recovery.
- Response validation.
- OHLC geometry validation.
- Timestamp ordering.
- Duplicate removal.
- Volume handling.
- Freshness marking.
- Delayed-data marking.
- Adjusted/unadjusted marking.
- Provenance.
- Regional handling.
- Health metrics.
- Unit, fixture, malformed, timeout, 429, 5xx, unknown-symbol and live/public/sandbox tests.

## 41.5 Data truth rules

- Required timeframes are fetched before optional timeframes.
- Use at most two compatible provider attempts per timeframe by default.
- Unknown symbols fail closed.
- Stale or delayed data cannot be silently used as real-time evidence.
- Provider-specific semaphores must be bounded.
- Cross-provider sanity checks must detect bad prints.
- WebSockets are an optimisation, not a correctness dependency.
- REST gap recovery must work.
- Every candle and quote must carry provenance.

## 41.6 Historical provider issues to re-test

- Binance may be regionally blocked.
- CoinGecko legacy experienced outages.
- yfinance experienced timestamp and outage problems.
- Bybit endpoint/category mapping previously required correction.
- Crypto WebSockets previously stalled and restarted.
- Provider outages must produce initial, 30-minute and 60-minute-plus alerts or the latest configured schedule.
- Recovery alerts must be emitted.
- Provider health must be exposed through Telegram diagnostics.

---

# 42. DYNAMIC ASSET DISCOVERY AND MARKET CAPABILITY

The system must:

- Discover assets dynamically.
- Maintain canonical asset registry.
- Track provider coverage.
- Track failing, quarantined, inactive and pending assets.
- Track liquidity and market-session status.
- Avoid repeatedly scanning unsupported assets.
- Avoid allowing discovery to expand memory or API usage without limits.
- Expose diagnostics through `/assets`, `/asset_capability`, `/asset_class_test`, `/all_asset_test_status` and related owner/admin surfaces.
- Support discovery snapshots and refresh.
- Keep owner-beta universe bounded.
- Preserve discovered asset state across restart.
- Correctly distinguish tradable, analysis-only and unsupported instruments.

---

# 43. STRATEGY INVENTORY AND DECISION INTELLIGENCE

## 43.1 Required strategy families

Support or explicitly classify:

- Trend Following.
- Mean Reversion.
- Breakout.
- Momentum.
- Scalping.
- Market Structure.
- ICT.
- Smart Money Concepts.
- Order Blocks.
- Liquidity Sweeps.
- Fair Value Gaps.
- VWAP.
- Volume Profile.
- Institutional Momentum Pulse.
- Fibonacci confluence.
- Wyckoff.
- Grid.
- Pairs Trading.
- Statistical Arbitrage.
- Options Flow.
- Macro.
- News.
- Crypto liquidity squeeze/breakout.
- Forex session fade.
- Commodity value rotation.
- Equity macro trend/pullback.
- Multi-timeframe consensus.
- Regime-aware strategy selection.

Advanced or weakly proven strategies such as grid, pairs, statistical arbitrage and options flow should remain paper/shadow until evidence supports promotion.

## 43.2 Multi-timeframe interpretation

The engine must distinguish:

- A true reversal.
- A lower-timeframe pullback within a higher-timeframe trend.
- Counter-trend opportunities.
- Trend continuation.

Example historical requirement:

- A 5-minute SELL inside 1-hour/4-hour BUY context may be labelled a pullback/counter-trend trade with reduced confidence instead of being misrepresented as full bearish alignment.

## 43.3 Decision records

Every important candidate branch must be explainable:

- Issued.
- Rejected.
- Skipped.
- Delayed.
- Suppressed.
- Quarantined.
- Provider-invalid.
- Risk-blocked.
- Tier-ineligible.
- Cooldown-blocked.
- Gemini-vetoed.
- ML-blocked.
- Resource-deferred.

Persist:

- Strategy contributions.
- Risk decisions.
- Regime.
- News.
- AI/ML.
- Provider quality.
- Context.
- Reasons.
- Timestamps.
- Versioned metadata.

## 43.4 Scoring

Separate:

- Raw strategy score.
- Technical score.
- Regime score.
- Multi-timeframe score.
- Liquidity/spread.
- News.
- On-chain.
- ML.
- Gemini review.
- Provider confidence.
- Delivery score.
- Display score.

Display score cap:

- 99.5 maximum.

Do not let Gemini or sentiment turn a weak technical signal into a strong one.

## 43.5 Expectancy and adaptive learning

- No hard-coded average win/loss.
- Use provenance-qualified R-multiples.
- Require a minimum sample.
- Keep live, paper, shadow and backtest expectancy separate.
- Missing data must not become zero.
- Use outcome history to improve strategy weights, target shaping, expiry and risk only through governed promotion.
- Do not automatically rewrite production strategy rules from a small sample.

---

# 44. SIGNAL PIPELINE, RISK, DEDUPLICATION AND DELIVERY

## 44.1 Pipeline

Canonical stages:

1. Resolve universe.
2. Resolve market session.
3. Fetch required data.
4. Validate data.
5. Generate candidates.
6. Persist rejection/decision telemetry.
7. Apply regime/MTF/confluence.
8. Apply liquidity/spread/microstructure.
9. Apply news/on-chain context.
10. Apply ML/Gemini review where enabled.
11. Apply risk and portfolio controls.
12. Apply deduplication/cooldowns.
13. Score/rank.
14. Store eligible signal.
15. Select audience.
16. Acquire user-specific reservation.
17. Fetch fresh final quote.
18. Validate price drift and geometry.
19. Send Telegram message.
20. Persist proof and active message.
21. Track lifecycle and outcomes.
22. Notify users.
23. Update reports and telemetry.

## 44.2 Risk requirements

Include:

- Valid entry, SL and TP geometry.
- Dynamic ATR-based targets and stops.
- Risk/reward thresholds.
- Spread.
- Slippage.
- Liquidity.
- Expected hold time.
- Time to target.
- Session.
- Expiry.
- Exposure limits.
- Per-asset limits.
- Per-direction limits.
- Per-class limits.
- Correlation/concentration.
- Account risk for execution.
- Daily loss/drawdown/open-position limits.
- Fail closed for execution.

## 44.3 Deduplication and locking

Implement:

- Full fingerprint deduplication.
- Asset/timeframe/direction/strategy checks.
- Active asset lock.
- Per-user four-hour asset repeat lock.
- Timeframe cooldowns.
- In-flight reservation.
- User-specific delivery idempotency.
- TradingView idempotency.
- Payment idempotency.
- Broker-order idempotency.
- Redis and database reconciliation.

## 44.4 Queue and fan-out

Historical problem:

- Later users could receive `expired_in_queue` because fan-out was sequential and DB-heavy.

Required fix:

- Batch-load user tiers, preferences, quotas and previous deliveries.
- Avoid N+1 queries.
- Use bounded send concurrency.
- Respect Telegram global and per-chat limits.
- Honour RetryAfter.
- Calculate queue validity from actual signal expiry and fresh quote, not only time spent waiting.
- Preserve fairness.
- Reconcile uncertain sends.
- Dead-letter permanently failed deliveries.

## 44.5 Production truth

A signal is not delivered merely because it exists in the signal table.

Proof requires:

- `sent_ok=true`.
- Telegram chat ID.
- Telegram message ID.
- Send timestamp.
- Delivery record.
- Active-message persistence where applicable.

Portfolio exposure, cooldowns, quarantine and live performance must use delivery-proof-backed records.

---

# 45. SIGNAL LIFECYCLE, OUTCOMES AND PERFORMANCE TRUTH

## 45.1 Canonical lifecycle

Support:

- CANDIDATE
- REJECTED
- STORED
- RESERVED
- SENT
- DELIVERED
- WATCHING_FOR_ENTRY
- ENTRY_TOUCHED
- ACTIVE
- TP1
- TP2
- TP3
- STOPPED
- MISSED_ENTRY
- EXPIRED
- CANCELLED
- INVALIDATED
- ARCHIVED

Transitions must be atomic and valid.

## 45.2 Outcome rules

- TP milestones are wins according to the canonical reporting policy.
- SL is a loss.
- Partial TPs are partial outcomes with correct realised R.
- Missed entry is not a win or loss.
- Expiry is not a win or loss unless an explicitly documented method states otherwise.
- Notify users of TP, SL, missed entry and expiry.
- Track early-exit recommendations separately.
- Preserve same-candle TP/SL ambiguity policy.
- Track fees, spread, slippage and latency where relevant.
- Do not hide losses or expired setups.

## 45.3 `/signals` behaviour

Historical requirement:

- `/signals` should show signals actually delivered to the requesting user.
- Use `signal_deliveries` with `sent_ok=true`.
- Default to active signals from the last seven days.
- Support filters such as:
  - today
  - week
  - 30d
  - active/running
  - closed
  - all
  - winners
  - losers
  - missed
  - asset

## 45.4 Early-exit intelligence

The system should notify when an opportunity materially changes before SL due to:

- Structure invalidation.
- Volatility collapse.
- Liquidity deterioration.
- Adverse macro/news.
- Benchmark breakdown.
- Provider/data uncertainty.
- Regime reversal.

Keep this separate from the official terminal outcome.

---

# 46. ML TELEMETRY, NEGATIVE DATASET AND MODEL GOVERNANCE

## 46.1 Collect, do not train heavily on the live monolith

The Railway monolith should collect structured telemetry continuously.

Large training, hyperparameter search, SHAP and bulk backtesting should run:

- Locally.
- In CI.
- In a dedicated analytics service.
- On a separate GPU/CPU worker.

## 46.2 Required telemetry

Track all candidates, especially rejected and near-miss candidates.

### Identity

- Candidate ID.
- Signal ID.
- Delivery ID.
- Asset.
- Canonical/provider symbol.
- Asset class.
- Market type.
- Exchange.
- Timeframe.
- Strategy and version.
- Direction.
- Evidence class.
- Generated timestamp.
- Rejection flag/stage/reason.

### Market context

- Entry candidate.
- Bid/ask/mid.
- Spread and spread bps.
- Volume and quote volume.
- Liquidity score.
- Quote/candle age.
- Provider latency.
- Normalised ATR.
- Realised volatility.
- Volatility/volume/trend regime.
- UTC hour.
- Day of week.
- Market session.
- Minutes from open/close.
- Benchmark asset.
- Benchmark slope.
- Beta.
- Correlation.
- Funding.
- Open interest.
- Liquidation imbalance.
- Order-book imbalance.
- News/macro risk.
- On-chain context.
- Provider confidence.
- Cross-provider disagreement.

### Technical setup

- EMA values including 200 EMA.
- Distance to 200 EMA.
- VWAP and distance.
- POC and distance.
- RSI.
- MACD and histogram.
- ADX/DMI.
- Bollinger width.
- Momentum/ROC.
- Body/wick ratios.
- Support/resistance.
- Order blocks.
- Liquidity sweeps.
- FVG.
- MTF consensus.
- Regime alignment.
- Confluence.
- Stop and target distances.
- R:R.
- Expiry.
- Expected hold time.
- Time-to-target.
- Score components.

### Delivery/operations

- Queue timestamp.
- Reservation timestamp.
- Send start.
- Send success.
- Queue wait.
- Telegram latency.
- Proof persistence.
- Retry count.
- RetryAfter count.
- Final quote drift.
- DB admission wait.
- Redis latency.
- Event-loop lag.
- Resource-governor state.

### Outcomes

- Entry-touch timestamp.
- TP timestamps.
- SL timestamp.
- Missed/expiry timestamp.
- Duration.
- Highest favourable/worst adverse price.
- MFE absolute, percentage and R.
- MAE absolute, percentage and R.
- Percentage toward TP1.
- Percentage of stop consumed.
- Time in profit.
- Time under water.
- Realised R.
- Partial R.
- Fees/slippage.
- Early-exit recommendation.
- Counterfactual outcomes clearly labelled.

## 46.3 Rejected signals

Rejected signals are a critical negative dataset.

Track:

- Candidates meeting most but not all conditions.
- Every rejection category through bounded sampling.
- Eventual shadow outcome where valid.
- Rejection policy version.
- Provider provenance.
- Valid geometry and expiry.

Never contaminate live performance with rejected/shadow outcomes.

## 46.4 Export and offline training

Export must:

- Stream in chunks.
- Avoid `fetchall()` for the full table.
- Support CSV and optional Parquet.
- Filter by date, strategy, asset class, evidence and outcome.
- Produce schema and checksum manifest.
- Anonymise users.

Offline training must include:

- Leakage audit.
- Time-based splits.
- Walk-forward validation.
- Calibration.
- ROC-AUC, PR-AUC and Brier.
- Expectancy by probability bin.
- MFE/MAE and time-to-resolution.
- Drawdown.
- Feature importance.
- Optional SHAP.
- Model metadata and rollback.
- No automatic production promotion.

---

# 47. NEWS, MACRO, ON-CHAIN AND GEMINI

## 47.1 News intelligence

Implement:

- Ingestion from credible sources.
- Normalisation.
- Deduplication.
- Reliability scoring.
- Asset mapping.
- Event timing.
- Sentiment/context.
- Historical impact tracking.
- Risk veto.
- Explainability.

Unverified rumours must not become facts.

## 47.2 On-chain intelligence

Where configured:

- Exchange flows.
- Whale movements.
- Funding.
- Open interest.
- Liquidations.
- Network activity.
- Context/veto rather than arbitrary score inflation.

## 47.3 Gemini

Gemini must have:

- Official SDK/API.
- Timeout.
- Bounded concurrency.
- Structured output.
- Validation.
- Caching.
- Candidate deduplication.
- Cost/token budget.
- 429 Retry-After.
- Process-level cooldown.
- Circuit breaker.
- Deterministic fallback.
- Prompt versioning.
- Audit trail.

Gemini failure must not crash deterministic signal processing.

---

# 48. TELEGRAM PRODUCT, COMMANDS, BUTTONS AND MESSAGING

## 48.1 Terms and disclaimers

- `/start` is gated by terms acceptance.
- `/about` and `/faq` must state that the platform provides signals/intelligence, not guaranteed profits.
- Users decide whether and how to trade unless they separately enable an approved execution mode.
- No misleading performance claim.

## 48.2 Free/public command catalogue

At minimum verify:

- `/start`
- `/help`
- `/about`
- `/faq`
- `/disclaimer`
- `/pricing`
- `/upgrade`
- `/tiers`
- `/signals`
- `/signal`
- `/proof`
- `/outcome`
- `/profile`
- `/profile_debug`
- `/invite`
- `/policy`
- `/refunds`
- `/recap`
- `/language`
- `/support`
- `/status`
- `/liveprice`
- `/market`
- `/myid`
- `/account`
- `/leaderboard`
- `/public_test_status`
- `/provider_health`
- `/performance_truth`
- `/receipt`
- `/receipts`
- `/report_issue`
- `/payment_help`
- `/refund_request`
- `/contact_admin`
- `/tester_feedback`
- `/paper_balance`
- `/paper_positions`
- `/paper_history`
- `/paper_performance`
- `/paper_reset`
- `/paper_settings`
- `/automaton_status`
- `/automaton_pause`
- `/automaton_resume`
- `/automaton_reset_paper`
- `/referral_leaderboard`
- `/referral_rewards`

## 48.3 Premium command catalogue

Verify:

- `/performance`
- `/stats`
- `/history`
- `/risk`
- `/alerts`
- `/analyze`
- `/dashboard`
- `/feedback`
- `/apikey`
- `/filter`
- `/reports`
- `/notify`
- `/portfolio`
- `/mission`
- `/quality`
- `/signal_quality`
- `/winrate`
- `/shadow_report`
- `/strategy_leaderboard`
- `/drawdown`
- `/setlot`
- `/mystats`
- `/referral`
- `/mt5`
- `/mt5link`
- `/mt5_link`
- `/mt5_status`
- `/connect_broker`
- `/cancel`

The historical `/filter` placeholder must be replaced with a real profile/preference workflow or removed from registration.

## 48.4 VIP command catalogue

Verify:

- `/simulate`
- `/setrisk`
- `/setwebhook`
- `/elite`
- `/early`
- `/report`

## 48.5 Admin command catalogue

Verify:

- `/admin`
- `/admin_dashboard`
- `/admin_broadcast`
- `/force_market_scan`
- `/force_signal`
- `/gemini`
- `/gemini_review`
- `/gemini_analyze`
- `/gemini_audit`
- `/gemini_predict`
- `/codex_audit`
- `/codex_log_review`
- `/codex_fix_plan`
- `/codex_security_scan`
- `/codex_release_check`
- `/codex_test_plan`
- `/codex_refactor_plan`
- `/codex_pr_summary`
- `/codex_generate_issue`
- `/admin_top_assets`
- `/admin_top_strategies`
- `/admin_user_engagement`
- `/admin_user`
- `/admin_subscription_fix`
- `/admin_signal_lookup`
- `/admin_feedback`
- `/admin_payment_lookup`
- `/admin_receipt_lookup`
- `/qa_report`
- `/selfcheck`
- `/ops_health`
- `/system`
- `/db_health`
- `/engine_debug`
- `/assets`
- `/release_guard`
- `/automaton_report`

## 48.6 Owner commands

Verify:

- `/dev_pause`
- `/dev_resume`
- `/dev_force_signal`
- `/dev_invalidate`
- `/owner_users`
- `/owner_revenue`
- `/version`
- `/correct_signal`
- `/provider_status`
- `/broadcast`

## 48.7 Owner-beta diagnostics

Verify:

- `/why_no_signal`
- `/delivery_eligibility`
- `/ohlc_health`
- `/asset_capability`
- `/asset_class_test`
- `/all_asset_test_status`
- `/owner_test_delivery`

## 48.8 Historical additional command ideas

Reconcile prior suggestions:

- `/mode`
- `/coach`
- `/replay`
- `/compare`
- `/market`
- `/leaderboard`
- `/report`
- `/signals`
- `/portfolio`

If not included, document why or map to existing aliases.

## 48.9 Buttons

Verify every visible button, including:

- Check Outcome.
- Open Signal.
- Monitor.
- Taking It.
- Watching.
- Manual/paper Take Trade.
- Profile controls.
- Pricing and upgrade.
- Receipt.
- Support.
- Paper controls.
- Broker controls.
- Pagination.
- Confirmation/cancel.

Every callback must:

- ACK immediately.
- Include enough identifiers.
- Validate role/user ownership.
- Be idempotent.
- Handle expiration.
- Handle duplicate clicks.
- Reject tampering.
- Work after restart where valid.

Historical bug:

- Button text/callbacks were observed not responding. Treat every button as broken until live tested.

---

# 49. PAPER TRADING, PORTFOLIO AND REPORTING

## 49.1 Paper trading

Implement:

- Virtual account.
- Configurable starting balance.
- Orders and fills.
- Positions.
- Spread, slippage and fees.
- Stops and targets.
- History.
- Performance.
- Reset.
- Settings.
- Per-user isolation.
- No crossover into live broker state.

## 49.2 Portfolio

Include:

- Active delivered signals.
- User-entered/manual trades where supported.
- Paper positions.
- Broker positions where linked.
- Exposure by asset/class/direction.
- Risk.
- Performance.
- Drawdown.
- Correlation.
- Pending outcomes.
- History.

## 49.3 Performance truth

Reports must distinguish:

- Live delivered.
- Paper.
- Shadow.
- Backtest.
- Walk-forward.
- Demo execution.
- Real execution.

Do not show a single blended win rate.

Include:

- TP1/TP2/TP3.
- SL.
- Missed.
- Expired.
- Partial wins.
- R.
- Fees.
- Slippage.
- Sample size.
- Methodology.
- Confidence.
- Date range.
- Provenance.

---

# 50. PAYMENTS, SUBSCRIPTIONS, REFERRALS, RECEIPTS AND SUPPORT

## 50.1 Paystack

Implement:

- Server-side initiation.
- Verification.
- Raw HMAC webhook verification.
- Event idempotency.
- Amount/currency/product verification.
- Entitlement activation.
- Expiry.
- Downgrade.
- Receipts.
- Refunds.
- Pending/failed states.
- Reconciliation.
- Admin lookup.
- Support flow.

Do not trust frontend payment success.

## 50.2 Referrals

Implement:

- Referral code/link.
- Attribution.
- Fraud controls.
- Reward rules.
- Leaderboard.
- Reward history.
- Tier/extra-signal rewards where business policy allows.
- No duplicate reward from replayed payments.

## 50.3 Extra signals

Historical concept:

- Purchase can grant one extra eligible signal.
- Must be the highest-scoring eligible ongoing signal not already delivered to the user.
- Must still pass freshness, risk, profile and deduplication.

## 50.4 Support

Support flows should include:

- Issue report.
- Payment help.
- Refund request.
- Contact admin.
- Tester feedback.
- Status and trace IDs.
- Admin case lookup.
- No exposure of secrets or other users.

---

# 51. MT5, METAAPI, COPY TRADE, AUTO-EXECUTION AND SMART DCA

## 51.1 Product intent

Users may receive:

- Signals only.
- Paper execution.
- Demo execution.
- Copy trading.
- Auto-execution.

Availability depends on tier, consent, account, risk policy and release stage.

## 51.2 MetaApi/MT5

Implement:

- Account linking.
- Credential encryption.
- Demo/live classification.
- Account information.
- Quotes.
- Symbol specification.
- Balance/equity.
- Margin.
- Positions.
- Orders.
- Place/modify/close.
- History.
- Reconciliation.
- Reconnect.
- Broker rejection.
- Symbol mapping.

Railway Linux cannot directly run the normal Windows MT5 terminal without an external bridge. Use MetaApi or a valid remote bridge.

## 51.3 Execution safety

Require:

- Global execution flag.
- User flag.
- Eligible tier.
- Explicit consent.
- Valid encrypted credential.
- Demo/live policy.
- Kill switch.
- Daily loss.
- Drawdown.
- Position limits.
- Fresh quote.
- Spread/slippage.
- Market open.
- Symbol min/max/step.
- Stop/freeze levels.
- Margin.
- Idempotency.
- Resource health.
- Broker health.
- Reconciliation.

Never use:

- Fake balance.
- Default `0.01` lot after error.
- Missing symbol spec.
- Stale quote.
- Incorrect `long`/`short` mapping.

## 51.4 Smart DCA

Requirements:

- No hard-coded user/account.
- Use delivery-proof-backed signals.
- Real broker specifications.
- Correct DCA1 → DCA2 progression.
- Async Redis calls must be correct.
- Bounded number of additions.
- Total risk cap.
- No martingale.
- Per-user/signal idempotency.
- Kill switch.
- Demo-first.
- Full audit/reconciliation.

## 51.5 Copy trading

Implement but keep gated:

- Master/follower mapping.
- Explicit consent.
- Fixed-risk or proportional sizing.
- Symbol mapping.
- Currency conversion.
- Max slippage.
- Min lot handling.
- Follower-specific limits.
- Partial failures.
- Idempotency.
- Reconciliation.
- Opt-out.
- Emergency stop.
- Demo mode.

---

# 52. AUTOMATON, AGENT COUNCIL AND AI ASSISTANT

The system may include:

- AI assistant.
- Automaton.
- CodexOps.
- Agent Council.
- Operational recommendations.
- Strategy audit.
- Feature discovery.
- Code-quality prompts.
- Incident summaries.

They may:

- Analyse.
- Recommend.
- Produce read-only audits.
- Surface technical debt.
- Rank improvements.
- Review logs.
- Suggest code changes.

They must not autonomously:

- Deploy production code.
- Change secrets.
- Move money.
- Enable execution.
- Place trades.
- Lower risk gates.
- Rewrite evidence.
- Change billing.
- Broadcast to users.

---

# 53. RAILWAY TARGET ARCHITECTURE

## 53.1 Initial topology

Use:

- One Railway application service.
- One Python process.
- One Uvicorn worker.
- One canonical FastAPI application.
- PostgreSQL.
- PgBouncer-compatible database URL.
- RedisState.
- RedisDelivery.

Avoid a multi-process monolith unless ownership and memory are independently proven.

## 53.2 Runtime ownership

Explicit owners for:

- Gateway/webhook.
- Telegram.
- Engine.
- Delivery.
- Outcome.
- Provider monitor.
- WebSockets.
- Payments.
- Scheduler.
- Waitlist.
- Resends.
- Free distribution.
- Shadow.
- ML.
- Drift.
- Asset learning.
- Reconciliation.
- Recovery.

No duplicated ownership.

## 53.3 Safe baseline environment

Reconcile with code:

- `PUBLIC_TESTING_MODE=0`
- `AUTO_MIGRATE=0` except one controlled migration deploy.
- `UVICORN_WORKERS=1`
- DB pool size 2.
- DB overflow 0.
- DB session cap 2.
- Background cap 1.
- Redis pool 24.
- Webhook workers 4.
- Queue 1000.
- Universe cap 18 for owner beta.
- Batch size 6.
- Market-fetch concurrency 2.
- REST-first owner beta.
- WebSockets off initially.
- Heavy ML/analytics off.
- Real execution off.
- Public payments off.
- Real payouts off.

## 53.4 Resource governor

Measure:

- RSS.
- Cgroup limit.
- CPU.
- Event-loop lag.
- DB admission.
- Redis latency.
- Queue depth.
- Provider errors.
- RetryAfter.
- Pending tasks.

States:

- OPTIMAL.
- CONSERVATIVE.
- MINIMAL.
- CRITICAL.

Protect:

- Health.
- Webhook ACK.
- Telegram commands.
- Delivery proof.
- Existing lifecycle tracking.
- Payment webhooks.
- Broker reconciliation.
- Kill switches.
- Database truth.

## 53.5 Deployment progression

1. Local tests.
2. Clean-room deployment.
3. Railway staging.
4. Owner-only crypto profile.
5. Same-signal lifecycle proof.
6. 24–72-hour soak.
7. Expand universe 18 → 30.
8. Add FX.
9. Add commodities.
10. Add stocks.
11. Add indices.
12. Add derivatives.
13. Enable one WebSocket provider at a time.
14. Paystack test beta.
15. Limited public advisory.
16. Paper/demo broker.
17. Collect at least 100 proof-backed live outcomes.
18. Offline ML training.
19. Controlled model promotion.
20. Separate real-execution release.

---

# 54. HISTORICAL INCIDENTS, BUGS AND REGRESSIONS TO RE-VERIFY

The implementation agent must treat these as regression requirements even when current tests pass:

1. PostgreSQL pool exhaustion and “too many clients”.
2. `/portfolio`, `/history`, `/admin_top_strategies`, `/codex_audit` failing under DB pressure.
3. Broadcast failures.
4. Signals generated but not delivered to owner.
5. `/signals` showing stored signals instead of delivered-to-user signals.
6. Telegram inline buttons and button text not responding.
7. Callback routes missing or mismatched.
8. Provider outages and restart thrashing.
9. yfinance timestamp normalisation errors.
10. CoinGecko legacy outages.
11. Redis hard-coded connection pool near 200.
12. Background jobs globally skipped during critical activity.
13. Rejection telemetry dropped under pressure.
14. Portfolio naïve/aware datetime mismatch.
15. Stored-but-undelivered rows counted as exposure.
16. Empty Redis causing durable signals to expire.
17. Segment quarantine using undelivered outcomes.
18. Gemini 429 cooldown not persisting.
19. Missing `decision_log.created_at`.
20. Synthetic ML bootstrap replacing production model.
21. Stale-learning wrong-class `persist_rejection`.
22. `web/app.py` regressed to an incomplete Flask app.
23. Root mount intercepting TradingView route.
24. Undefined TradingView functions.
25. Waitlist scheduler imports/jobs missing.
26. MetaApi execution without live quote.
27. Account info retrieval missing.
28. Risk percentage not loaded from DB.
29. Fallback `0.01` lot.
30. Bybit endpoint/category bugs.
31. Derivatives classified as spot.
32. Smart DCA broken import.
33. Smart DCA wrong Redis async use.
34. Smart DCA unable to advance steps.
35. Smart DCA hard-coded account.
36. Hard-coded expectancy averages.
37. Unsafe native MT5 fake balance.
38. Incorrect long direction.
39. Broker login config unused.
40. Missing geometry validation.
41. Queue expiry for later users.
42. Fan-out N+1 DB queries.
43. Full ML stack loaded on production startup.
44. Local `telegram` package shadowing `python-telegram-bot`.
45. `datetime.utcnow()` inconsistency and deprecation.
46. Disabled ML archive job still doing startup work.
47. Provider fallback accepting stale/delayed data as live.
48. Same signal ID not proven across delivery and outcome lifecycle.
49. Waitlist jobs unavailable in logs.
50. WebSocket stalls.
51. Trading preferences deferred unexpectedly.
52. Token-rotation test weakened to accept 401 rather than proving authenticated success.

For token rotation:

- Separate unauthenticated 401 test.
- Authenticated success test.
- Invalid token test.
- Revoked/replayed token behaviour.
- Never accept 401 as equivalent to successful rotation.

---

# 55. TESTING MUST PROVE THE FULL SYSTEM, NOT MERELY FEATURES

The implementation agent must use the v4 testing contract and additionally prove:

## 55.1 Complete integrated bot test

One test orchestration must run:

- FastAPI application.
- PostgreSQL/PgBouncer.
- RedisState.
- RedisDelivery.
- Telegram test bot.
- Provider connections.
- All tiers.
- All profiles.
- All enabled asset classes.
- All strategies.
- Delivery.
- Callbacks.
- Lifecycle.
- Outcomes.
- Paper.
- TradingView.
- Paystack test.
- MetaApi demo where available.
- Restart and recovery.

## 55.2 All-asset representative tests

Use representative instruments such as:

- BTC spot.
- BTC perpetual.
- A crypto option where supported.
- EUR/USD.
- Gold/XAU or a supported gold future.
- A liquid stock.
- An S&P 500 index representation.
- A supported derivative.
- Broker synthetic only if demo broker exposes it.

A valid rejection is acceptable if:

- Data fetch succeeds.
- Decision pipeline succeeds.
- Rejection reason is correct.
- Telemetry is persisted.

## 55.3 Every profile and tier

Run pairwise/full combinations across:

- Profile.
- Tier.
- Timeframe.
- Asset class.
- Strategy.
- Direction.
- Session.
- Provider.
- Outcome.
- Resource state.

## 55.4 Live external certification

Mocks are not enough.

Use safe live/public/sandbox calls for:

- PostgreSQL.
- Both Redis.
- Telegram.
- Providers.
- Gemini.
- TradingView.
- Paystack test.
- MetaApi demo.

## 55.5 Production evidence

Require:

- Clean-room deployment.
- Railway staging.
- Same-signal proof.
- Restart proof.
- Redis flush recovery.
- Queue recovery.
- Provider failure recovery.
- Load/latency.
- Chaos.
- 24–72-hour soak.

---

# 56. ADDITIONAL GAP-CLOSURE REQUIREMENTS

## 56.1 Data retention and archive

Implement configurable retention without deleting critical evidence.

- Archive old delivery attempts, logs and resolved operational records.
- Keep financial/payment audit records according to legal/business policy.
- Keep ML telemetry needed for training.
- Keep delivery proof and performance provenance.
- Use partitioning/archive tables/object storage where appropriate.
- Dry-run and report purge operations.
- Never use a generic delete against the canonical signal ledger without explicit evidence and backup.

## 56.2 Docker and dependency optimisation

- Multi-stage Docker build where beneficial.
- Pinned Python.
- Reproducible dependency lock.
- No build cache.
- Non-root where compatible.
- Remove compilers from runtime image.
- Lazy optional heavy imports.
- Measure image size and memory.
- Keep NumPy/pandas/ML imports out of the hot startup path when not required.

## 56.3 Sentry and alert quality

- Do not simply discard every timeout/429/502.
- Categorise expected provider/network events.
- Aggregate noisy transient errors.
- Preserve representative events and metrics.
- Always report unhandled application bugs, repeated degradation, data corruption and failed recovery.
- Include trace IDs.

## 56.4 WebSocket supervision

- Backoff with jitter.
- Heartbeats.
- Stale detection.
- Sequence handling.
- Gap recovery.
- Bounded buffer.
- Circuit breaker.
- No reconnect storm.
- Resource-aware disable.
- REST correctness fallback.

## 56.5 Security and compliance

Complete:

- Secrets.
- Encryption.
- Key rotation.
- HMAC.
- Replay protection.
- Rate limits.
- RBAC.
- IDOR.
- SQL injection.
- SSRF.
- Callback tampering.
- CORS.
- Log redaction.
- Export authorisation.
- Retention policy.
- Privacy notice.
- Audit logs.
- No raw token storage.
- No unsafe model deserialisation.

## 56.6 Cost control

Track and limit:

- Provider quotas.
- Gemini usage.
- Railway CPU/memory.
- PostgreSQL storage/connections.
- Redis memory.
- Logs.
- Telegram sends.
- Background analytics.
- Export jobs.

Expose owner diagnostics and alerts before quota exhaustion.

---

# 57. MANDATORY PERMISSION AND INFORMATION REQUEST

At the start, create one consolidated request for all missing live-test inputs:

## Repository and Railway

- Latest repository or GitHub access.
- Railway project/staging access.
- Permission to deploy staging.
- Permission to read logs.
- Database backup confirmation.

## Telegram

- Test bot token.
- Test chat/group.
- Test user IDs for all tiers.
- Permission to register webhook.
- Permission to send only to test users.

## Infrastructure

- PostgreSQL service.
- RedisState.
- RedisDelivery.
- Public staging domain.

## Provider credentials

Request only those selected for certification:

- Alpha Vantage.
- Twelve Data.
- EODHD.
- Marketstack.
- Finnhub.
- FMP.
- Tiingo.
- Polygon.
- Alpaca.
- OANDA.
- Tradier.
- Other required providers.

## Other integrations

- Gemini API key and budget.
- TradingView secret.
- Paystack test keys.
- MetaApi token and demo account.
- Encryption key set in Railway.
- Owner/admin Telegram IDs.
- Current tier prices and periods.
- Data-retention decision.
- Support/contact information.

Secrets should be placed directly into sealed Railway variables, not pasted into chat.

---

# 58. FINAL DELIVERABLES FOR AN AI WITH NO CHAT ACCESS

The agent must return:

1. Full updated repository ZIP.
2. Patch from baseline.
3. Git commit history or clear commits.
4. SHA-256 checksums.
5. Universal Requirement Register.
6. Cross-Chat Decision Ledger using this addendum as the historical source.
7. Repository Proof Manifest.
8. Requirement-to-code-to-test matrix.
9. Feature Coverage Matrix.
10. Provider Certification Matrix.
11. Asset-Class Matrix.
12. Profile Matrix.
13. Tier Matrix.
14. Command/Callback/Button Matrix.
15. Strategy Matrix.
16. Database/schema catalogue.
17. Environment contract.
18. Railway env profiles.
19. Provider key template.
20. Migration report.
21. Coverage and mutation reports.
22. Static/security/dependency reports.
23. Full-system orchestrator report.
24. External-connection report.
25. Chaos/recovery report.
26. Load/latency report.
27. Clean-room deployment report.
28. Railway staging report.
29. Same-signal lifecycle evidence.
30. Soak report.
31. Permission and blocker register.
32. Rollback and incident runbooks.
33. Exact deployment steps.
34. Exact owner actions still required.
35. Honest evidence-based release verdict.

The agent must not return another broad “code complete” summary unless these artefacts and required evidence exist.

---

# 59. FINAL COMPLETION RULE

The project is not complete merely because:

- Unit tests pass.
- 642 or any other number of tests pass.
- Two test files were changed.
- The application starts.
- Health returns 200.
- A signal is generated.
- A Telegram message is sent.
- A provider returns data.
- A demo order works once.
- Documentation exists.

The project is complete only for the exact claimed release stage when:

- All known requirements in v4 and this addendum are implemented.
- No unresolved critical/high defect remains.
- Every enabled provider is certified.
- Every enabled asset class works end to end.
- All profiles and tiers work end to end.
- Every command and button works.
- Complete-system orchestration passes.
- State and queues recover.
- Payments and demo broker flows reconcile.
- Security, coverage and mutation gates pass.
- Railway staging passes.
- Same-signal lifecycle proof passes.
- Required soak passes.
- Completion Defence Package exists.
- Any blocked feature is disabled and excluded from the claimed release scope.

Allowed final statuses:

- WORK_IN_PROGRESS
- CODE_COMPLETE_BUT_LIVE_PROOF_PENDING
- BLOCKED_BY_OWNER_PERMISSION
- BLOCKED_BY_MISSING_CREDENTIAL
- BLOCKED_BY_THIRD_PARTY
- STAGING_VERIFIED
- OWNER_BETA_VERIFIED
- LIMITED_PUBLIC_VERIFIED
- PAID_BETA_VERIFIED
- REAL_EXECUTION_VERIFIED

No other broad “perfect” or “100% production-ready” statement is permitted without the evidence to defend it.


---

# 36. FINAL INSTRUCTION

Build the system. Do not merely restate this prompt. Do not ask broad questions that can be answered by the supplied sources. Ask only one consolidated set of genuinely blocking business/credential/permission questions after completing everything possible without them. Preserve evidence, expose uncertainty, and keep dangerous features disabled until proven.
