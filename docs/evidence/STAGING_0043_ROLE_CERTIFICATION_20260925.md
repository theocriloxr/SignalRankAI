# Staging 0043 and Runtime-Role Certification — 2026-09-25

Scope: Railway project `trading-bot-account2`, environment `staging`.
Production was not deployed, migrated, or reconfigured by this certification.

## Database migration

The isolated migration owner upgraded the active staging PostgreSQL database
from `0042_ml_recovery_provenance` to `0043_account_execution_policy`.

- migration deployment: `ec5be43c-0658-4398-93fc-50917b387158`
- expected/current Alembic head: `0043_account_execution_policy`
- post-migration schema gate: PASS
- post-migration staging runtime proof: PASS
- proof blockers: none
- global execution kill switch: enabled
- real execution, automatic execution, copy trading, live MT5/Bybit,
  Hyperliquid mainnet, real payouts and Paystack transfers: disabled

The staging database identity reported by the schema gate was the same database
used by the existing staging runtime.

## Clean-room release evidence

Commit `f36ea5ca49c4e0b9077fe5a86d8e372c2438ed65` passed the zero-secret
clean-room verifier:

- exact 0043 Alembic release chain: PASS
- schema audit including append-only/idempotent trading-account ledger: PASS
- targeted multi-account / risk / security / readiness / quiescent suite:
  **241 passed**
- final marker: `CLEANROOM_PASS`

## Quiescent staging role proofs

Quiescent certification runs only after release-source and read-only schema
admission. It binds a health endpoint but does not start market scanning,
signal generation, Telegram business work, delivery work, outcome tracking,
analytics/ML training, broker execution, payments, or payouts.

| Role | Deployment | Commit | Result |
|---|---|---|---|
| Analytics | `284ed63b-0716-48e4-9498-41dc270c0e6f` | `0463c78fdf7b...` | PASS |
| Engine | `a67a3f14-5944-4e27-b8c3-245c1a3bd96b` | `0463c78fdf7b...` | PASS |
| Delivery / worker | `d4a490dc-ce9f-4e30-9fae-172ac94cbe3f` | `f36ea5ca49c4...` | PASS |
| Frontdoor | `a562a609-b533-46e9-aa2b-bbffcc5bbdc4` | `f36ea5ca49c4...` | PASS |

Each role proved:

1. exact release-source identity;
2. Alembic current = expected = 0043;
3. every required account-policy/reconciliation/ledger/provenance schema object;
4. staging-only environment/profile;
5. global execution kill switch enabled;
6. all live-money/broker/payout switches disabled;
7. role ownership resolves without hidden `all/dev` monolith fallback.

## Active staging runtime cutover

The long-lived staging roles were cut over only after their exact rollout
commit passed the zero-secret clean-room verifier. Production remained isolated
through service watch patterns and did not deploy any staging rollout marker.

| Role | Railway service | Deployment | Commit | Runtime proof |
|---|---|---|---|---|
| Analytics | `signalrankai-analytics` | `af352868-be5d-4012-90fc-ca56dc06252f` | `3a1e07238d4966...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=analytics`; locked dependency graph; analytics tasks active |
| Delivery / outcome worker | `bountiful-miracle` | `0e82f4b8-d4d9-4bf7-bcfe-a87e3a8be044` | `3b5ff87e7e8e...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=delivery`; locked dependency graph; delivery/outcome/paper/MT5 reconciliation active |
| Signal engine | `striking-optimism` | `de79e783-f33a-4cc2-8871-b6f3bc60c470` | `b6bfdec42bec43...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=engine`; locked dependency graph; bounded adaptive-candle DB-pressure fix active |
| Frontdoor | `SignalRankAI` | `a3d77cb6-5933-4634-83be-56b6b6426702` | `4e6575df5dea78...` | release/source PASS; Alembic 0043; schema PASS; frontdoor DB admission; Uvicorn/Telegram webhook healthy; `/healthz` 200; locked dependency graph |

The role commits intentionally differ because the engine carries one later
staging-only application fix (`4480625`): adaptive candle persistence now yields
under foreground DB pressure, bounds snapshots per transaction and PostgreSQL
waits, and requeues the complete failed batch. The dependency-lock commits are
shared across all four active roles. Rollout marker commits remain isolated by
role-specific `staging-rollout/runtime/<role>/**` watch paths.

### Locked dependency and adaptive-candle pressure proof

The active staging roles install the certified `requirements.lock` graph with
`pip install --no-deps -r requirements.lock` followed by `pip check`.
The latest engine image passed **277 build-time tests** plus all 12
production-readiness checks.

Engine deployment `de79e783-f33a-4cc2-8871-b6f3bc60c470` additionally proved:

- DB admission: session limit 2, foreground reserve 1, background limit 1;
- noncritical candle persistence yields immediately while foreground DB work
  owns the reserved lane instead of blocking the engine;
- deferred snapshots are requeued rather than silently discarded;
- when capacity returned, a bounded batch persisted
  `2 snapshots / 400 candles`;
- candle fetch remained responsive (`5/5` assets succeeded at concurrency 2);
- no warning/error-severity logs were emitted during the observed interval.

Observed `NoncriticalWriteDropped` entries are expected backpressure evidence,
not data-loss evidence: the complete failed batch is restored to the in-process
queue and later retried.

### Engine multi-asset proof

The active engine reported an all-class profile demand snapshot with six active
profiles and classes `crypto`, `fx`, `commodity`, `index`, and `stock`.
Provider discovery reported usable coverage for:

- 250 crypto instruments from the database registry;
- 16 FX instruments from provider discovery;
- 23 equities from provider discovery;
- 5 indices from provider discovery;
- 4 commodities from provider discovery.

The first post-cutover cycle was correctly crypto-heavy because it ran after
the Friday close. Runtime market calendars explicitly rejected the non-crypto
instruments for closed-market reasons: FX and commodities after 22:00 UTC,
US/UK/European cash indices outside their local sessions, and US equities
outside the New York cash session. This is evidence of market-hours gating,
not a crypto-only universe defect.

### Public frontdoor proof

The frontdoor startup reported:

- `runtime_ownership mode=frontdoor`;
- `http=true`, `telegram=true`, `scheduler=true`;
- `engine=false`, `worker=false`;
- Uvicorn listening on port 8080;
- Railway `GET /healthz` returned HTTP 200;
- Telegram handlers registered and webhook mode active;
- webhook URL already registered at the staging Railway domain;
- webhook pending count = 0 and no last webhook error.

An independent browser fetch of the public staging domain also returned
`{"status":"ok", ... "resource_state":"OPTIMAL"}` from `/healthz`.
The public root rendered the SignalRankAI command centre in PAPER mode with
execution shown as DISABLED.

### Financial safety and production isolation

Throughout migration, certification and active staging cutover:

- `GLOBAL_EXECUTION_KILL_SWITCH=1`;
- live financial master switch off;
- real/automatic/copy execution off;
- live MT5 and Bybit execution off;
- Hyperliquid mainnet execution off;
- real/automatic payouts off;
- Paystack transfers and public payments off;
- boot-time database migrations off on normal runtime roles.

The production environment received the staging rollout commits only as
`SKIPPED` deployments. No production service was redeployed and no production
database migration was performed.

## Cutover boundary

Staging business-loop cutover is now verified for analytics, delivery, engine
and frontdoor on the 0043 architecture. This evidence still does **not** enable
live money, PROP execution, real payouts, or production deployment. Demo/live
broker certification and owner-controlled financial activation remain separate
gates.
