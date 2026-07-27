# SignalRankAI Capacity Model

Date: 2026-07-25
Status: Locally modelled; live infrastructure validation remains required.

## Capacity definitions

SignalRankAI distinguishes registered accounts, daily active users, concurrent logical sessions, inbound Telegram update bursts, users eligible for one signal, web/API concurrency, and concurrent market-data work. These are different workloads and must not be represented as one number.

The target of 100,000 users means the platform must be able to store and resolve 100,000 user profiles and safely plan a delivery fanout to 100,000 eligible recipients. Telegram network throughput is bounded by Telegram limits and must use durable queued delivery rather than an instant broadcast claim.

## Local fanout-planning evidence

The deterministic delivery planner was exercised with:

- Users: 100,000
- Shards: 32
- Maximum batch size: 100
- Batches: 1,015
- Duplicate recipients: 0
- Missing recipients: 0
- Elapsed planning time: 0.3579 seconds
- Peak memory: 9.02 MB
- Real Telegram requests: disabled

This proves bounded fanout planning, deterministic sharding, and duplicate-free coverage. It does not prove Telegram send throughput, Railway replica throughput, database throughput, or external-provider quotas.

## Scale stages

| Stage | Registered users | Expected release mode | Suggested runtime shape | DB/Redis posture | Required proof before promotion |
|---|---:|---|---|---|---|
| 1 | 1,000 | Owner/internal and small beta | 1 ingress, 1 engine, 1 delivery, 1 outcome worker | Managed Postgres, PgBouncer, managed Redis | End-to-end delivery proof, restart recovery, 24-72 hour soak |
| 2 | 10,000 | Limited/paid beta | 2 ingress, 2-4 delivery workers, isolated engine/outcome roles | Connection-budget dashboards, queue lag alerts | Load test at 2x expected peak, provider quota evidence |
| 3 | 25,000 | Controlled production | Horizontally scaled ingress and delivery shards | Read-heavy caching, background-query isolation | Chaos tests, restore drill, delivery SLA evidence |
| 4 | 50,000 | Expanded production | Multiple delivery partitions and independent maintenance workers | Consider read replica for analytics | Sustained soak under command-plus-fanout contention |
| 5 | 100,000 | Scaled production | Stateless ingress, durable queue consumer groups, 32+ logical delivery shards | HA Postgres/PgBouncer and HA Redis where justified | Real infrastructure load report, cost model, incident drill, no unresolved P0/P1 issues |

## Database connection budget

Each deployable role must have an explicit connection budget. Staging remains conservative (`pool_size=2`, `max_overflow=0`) to expose session misuse. Production pool sizes must be derived from the managed Postgres connection limit and replica count; they must not be increased to hide long transactions. PgBouncer transaction pooling is recommended before large horizontal scale.

## Queue and delivery model

- One canonical signal is generated once.
- User eligibility is resolved in bounded pages.
- Delivery jobs are sharded deterministically.
- Each `(signal_id, user_id)` is idempotently reserved.
- Telegram rate limiting and `RetryAfter` are respected.
- Progress is durable and resumable.
- A successful Telegram send is not complete until proof and message metadata are persisted.
- Partial success enters reconciliation and is never blindly resent.

## Market-data capacity

Market-data concurrency is intentionally independent from user count. A signal is computed once per asset/timeframe and distributed to eligible users. The staging defaults enforce two asset fetches at once, provider-specific semaphores, request coalescing, required-first timeframes, bounded fallback attempts, and cache reuse.

## Promotion thresholds

A scale stage is not approved by code presence alone. Promotion requires measured p50/p95/p99 latency, CPU, memory, DB connections, Redis throughput, queue lag, delivery failure rate, provider error rate, and cost. Any duplicate delivery, stale signal, missing proof, database exhaustion, or unbounded queue lag blocks promotion.
