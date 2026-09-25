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

## Cutover boundary

This evidence certifies branch/schema compatibility. It does **not** enable live
money, PROP execution, production deployment, or a staging business-loop
cutover by itself. Actual staging role cutover must preserve the same source,
schema and financial safety gates and must avoid duplicate ownership.
