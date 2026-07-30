# SignalRankAI v1.2.7 Outcome, Price, Adaptive-DB and Production-Gate Release Notes

Date: 2026-07-30  
Release fingerprint: `v1.2.7-outcome-price-production-gate-20260730`  
Migration head: `0027_launch_paper_trading`

## Why this release exists

The v1.2.6 Railway runtime proved that Telegram callback transport and handler registration were healthy, but it exposed several independent data-contract defects that made the system appear healthier than it was:

- the outcome worker repeatedly returned `active_scan fetched=0` while the engine retained proof-backed delivered signals;
- a delivered XAUTUSDT signal crossed entry, TP1 and TP2 but remained reported as active with no milestone notifications;
- monitor refreshes timed out or could not persist, and venue/source identity was not clear when comparing the bot with TradingView;
- `/adaptive_status` labelled a PostgreSQL query-typing defect as database connection pressure, and one Redis enqueue timeout caused the same Telegram update to be processed by both Redis and the local fallback queue;
- adaptive candle persistence repeatedly failed with asyncpg parameter-type ambiguity and generated excessive repeated writes;
- `/system` reported a Redis `TypeError` despite state Redis, delivery Redis and queue diagnostics passing;
- `/simulate` exposed zero completed evidence without distinguishing delivered-but-pending signals and partial TP milestones.

## Root-cause corrections

### 1. Delivered-signal outcome discovery

Delivery proof states are normalised case-insensitively across `sent`, `delivered`, `confirmed` and `reconciled`. Historical rows stored as uppercase `CONFIRMED` are now visible to:

- the background outcome scan;
- restart/backfill reconciliation;
- interactive Check Outcome reconciliation;
- lifecycle notification-recipient selection;
- paper-trading evidence queries.

A valid proof requires `sent_ok=true`, Telegram chat/message identifiers and a recognised delivery state.

### 2. Missed milestone reconciliation

Monitor and Check Outcome perform read-through reconciliation through the canonical lifecycle worker. One trusted price observation can sequentially persist missed milestones such as:

`entry_touched -> tp1_hit -> tp2_hit -> tp3_hit`

This repairs signals that moved through multiple levels while the previous worker query returned no rows. Notifications remain idempotent through durable event rows.

### 3. Fresh and attributable monitor prices

Monitor cards no longer use the legacy trade-tracker cache as their authoritative display price. They use:

1. a trusted outcome snapshot inside the configured age ceiling; or
2. a typed provider quote validated with the final-delivery trust contract.

The monitor now displays:

- provider name;
- provider symbol when it differs from the canonical asset, for example `okx (XAUT-USDT)`;
- source age;
- current price and live P/L;
- highest completed target and next target.

Legacy Redis ticks older than the configured maximum are rejected. A difference from TradingView can therefore be identified as venue/instrument spread rather than hidden as an unexplained stale price.

### 4. Webhook timeout duplicate prevention

A Redis enqueue timeout is an indeterminate result: the stream write may complete after the local wait expires. The previous fallback path could therefore enqueue the same update locally and later consume the Redis copy, producing duplicate command replies.

v1.2.7 no longer falls back locally after an indeterminate Redis timeout. It returns a retryable HTTP 503, allowing Telegram to retry while the Redis-stream idempotency key collapses any late success. Definite Redis failures may still use the bounded in-process fallback.

### 5. Adaptive status and error classification

`/adaptive_status` binds its optional asset parameter explicitly as PostgreSQL text. A missing asset no longer produces `could not determine data type of parameter $1`.

Command failures are classified as:

- actual database pressure;
- database/query defect;
- other application error.

SQL programming errors are no longer presented to users as connection exhaustion.

### 6. Adaptive candle persistence

The old repeated `INSERT ... SELECT ... WHERE NOT EXISTS` statement reused parameters with conflicting PostgreSQL types and attempted very large historical writes repeatedly.

v1.2.7 uses chunked PostgreSQL bulk upserts against the existing unique candle constraint. It queues only:

- a bounded initial history;
- newly completed candles;
- the current open candle at a controlled refresh interval.

This removes asyncpg `text versus character varying` ambiguity and substantially reduces write amplification and DB-lane contention.

### 7. `/system` reliability report

The Redis health check now uses valid redis-py timeout arguments and tests `STATE_REDIS_URL` before the general Redis URL. It runs blocking client operations off the event loop.

The delivered-without-outcome metric now counts only proof-backed, non-archived deliveries. It separately reports delivered signals still awaiting terminal outcomes, instead of presenting every legacy row as an active tracking failure.

The command also reports local pool/admission information and PostgreSQL capacity where available.

### 8. `/simulate` evidence transparency

Monte Carlo evidence uses only terminal delivered outcomes with an R multiple. TP1 and TP2 are lifecycle milestones, not completed trades, and are reported separately.

The insufficient-evidence response now distinguishes:

- completed delivered outcomes;
- total proof-backed deliveries;
- signals awaiting a terminal outcome;
- recorded TP1/TP2 milestones;
- paper equity and open paper positions.

No invented win rate or default reward distribution is introduced.

### 9. PostgreSQL production capacity gate

Deployment diagnostics now inspect:

- PostgreSQL `max_connections`;
- current database connections;
- the app's effective pool plus overflow;
- a reserved connection margin.

The production launch gate fails when there is insufficient headroom.

## Database architecture decision

Do **not** add a second writable database for this release. The observed failures were deterministic query/client defects plus write amplification, while schema/admission diagnostics passed.

The supported production topology is:

- one authoritative PostgreSQL primary for users, payments, subscriptions, delivery proofs, signals, outcomes and execution state;
- reviewed app pool limits for one Railway application replica;
- separate state and delivery Redis responsibilities;
- optional PgBouncer transaction pooling or a larger primary if measured headroom later becomes insufficient;
- optional read replica for analytics/reporting only;
- optional separate time-series/analytics store for historical candles and research only after dual-write/replay integrity is designed.

A second writable primary would introduce split-brain risks for payments, callbacks, subscriptions, deduplication and lifecycle events.

## Initial public-production boundary

The production profile enables:

- public tier-based signal delivery;
- live Paystack subscription payments;
- callback buttons and commands;
- lifecycle and outcome notifications;
- paper trading;
- manually linked demo execution;
- adaptive candle capture and research with human approval.

The initial public release keeps these disabled:

- unrestricted real broker execution;
- automatic live trading;
- copy trading;
- MT5 live accounts;
- Bybit execution;
- automatic bank payouts.

`REAL_PAYOUTS_ENABLED=0` remains required because the repository does not contain a fully runtime-certified Paystack Transfer disbursement adapter.

## Required Railway evidence before opening access

- exact v1.2.7 boot fingerprint;
- callback handler readiness of at least 60;
- `active_scan fetched` greater than zero when proof-backed active deliveries exist;
- reconciliation of signal `b15e7d94-9bf5-4cf6-8eaa-da842ccd9d7d`;
- persisted and sent entry/TP1/TP2 lifecycle events;
- `/monitor` showing a trusted provider, provider symbol and source age;
- `/adaptive_status` returning normally;
- no adaptive candle `AmbiguousParameterError`;
- `/system` reporting Redis connected and credible proof-backed backlog counts;
- `/simulate` reporting delivered, pending and milestone evidence correctly;
- `postgresql_capacity_headroom` passing;
- live Paystack key pair and signed webhook verification passing;
- no critical/high production-diagnostic failures.
