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
| Analytics | `signalrankai-analytics` | `3a1460b5-0f9a-4272-b5c3-b2fdb92253e3` | `eef229c4658003...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=analytics`; analytics tasks active |
| Delivery / outcome worker | `bountiful-miracle` | `681bb02a-4abc-49a9-98c3-37b341d83832` | `bcc6e235facfe82c...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=delivery`; delivery/outcome/paper/MT5 reconciliation active |
| Signal engine | `striking-optimism` | `3d0cb3c4-bbbe-4f02-8156-eb7308920509` | `6d12f5ad69eda516...` | release/source PASS; Alembic 0043; schema PASS; `run_mode=engine`; engine loop active |
| Frontdoor | `SignalRankAI` | `1598e967-7f6f-41ff-8ad9-36143d7aba02` | `61f3941021c574c...` | release/source PASS; Alembic 0043; schema PASS; `mode=frontdoor`; HTTP/Telegram/scheduler owned; engine/worker loops disabled |

The commit differences between these role deployments contain only
`staging-rollout/**` marker files. Git comparison showed no application-code
difference between the active analytics, delivery, engine and frontdoor SHAs.

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
