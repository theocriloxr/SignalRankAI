# Staging Demo Broker Account Preflight — 2026-09-27

Status: **BLOCKED_EXTERNAL**

Railway deployment: `9757cac0-7f68-466a-a9a0-8e458f1390cd`  
Rollout commit: `3656eabaf56a7468a49667e078289d4bf00028af`

## Purpose

This preflight answers one narrow question without placing any order or
returning any broker secret:

> Is there already a canonical staging DEMO account that is ready to enter the
> bounded demo-certification workflow?

The answer at the time of this run was **no**. The preflight process exited
non-zero by design because a BLOCKED certification preflight is fail-closed;
Railway therefore labels the short-lived job `CRASHED`, which is expected for
this blocked result and is not a frontdoor/runtime crash.

This refresh ran after the secure Broker Hub handoff rollout on frontdoor
deployment `68219e01-9b4a-48a8-8abb-9e4372f634f9` /
`c4d1e6d6ec5e...`. Telegram no longer accepts broker passwords in chat; the
linking path sends the authenticated user to Broker Hub so canonical account
ownership and credential-envelope storage remain server-bound.

That frontdoor passed Alembic `0045` schema admission, decomposed
`mode=frontdoor` ownership, **356 build tests**, all 12 readiness checks,
209-handler Telegram readiness, webhook pending=0 and `/healthz=200`.
Clean-room `c4d1e6d6...` passed **469 targeted tests**. The existing
preparation action still performs provider-backed read-only verification and
reconciliation, applies a bounded `DEMO/MANUAL` policy, and deliberately
leaves execution disabled. It cannot place an order or activate live money.

## Environment / schema evidence

- Environment: `staging`
- Current Alembic head: `0045_mt5_credential_retirement`
- Expected Alembic head: `0045_mt5_credential_retirement`
- Activation performed: **false**
- Orders placed: **0**
- Secrets returned: **false**

## Canonical account counts

- Total broker connections: **0**
- DEMO-policy connections: **0**
- Read-only verified DEMO connections: **0**
- Credential-ready DEMO connections: **0**
- HEALTHY-reconciled DEMO connections: **0**
- DEMO connections with explicit execution permission: **0**
- DEMO execution-enabled connections: **0**
- Frozen DEMO policies: **0**
- Provider/account rows returned: **none**

## Exact blockers

The preflight returned:

- `demo_account_not_connected`
- `demo_account_not_read_only_verified`
- `demo_account_credentials_not_ready`
- `demo_reconciliation_not_healthy`
- `demo_execution_permission_not_configured`

## Important credential boundary

Railway runtime services currently expose the **names** of environment-level
broker credential variables such as a MetaApi token and Bybit API key/secret.
Those variables are not proof of canonical account ownership, user consent,
account identity, DEMO classification or execution authorization.

SignalRank therefore does **not** silently transform global environment
credentials into a user's `broker_connections` row. Doing so would violate
the canonical ownership and wrong-account-execution protections.

## What is required next

An explicitly owned broker DEMO account must be connected through the canonical
web or Telegram broker-linking flow. After that:

1. use the canonical **Prepare DEMO certification** action; it re-runs
   provider-backed read-only verification/reconciliation and refuses any
   live/ambiguous account;
2. the preparation action applies a bounded `DEMO/MANUAL` policy while keeping
   execution **OFF** and without placing an order;
3. accept the execution-risk terms and separately enable only that DEMO account;
4. the account must remain unfrozen, reconciliation must be `HEALTHY`, and all
   deterministic risk/quote/session/market gates must continue to pass;
5. execute the bounded demo order / modify / close / reconciliation lifecycle
   through the canonical router;
6. retain broker acknowledgement, account-ledger, realized P/L/fee,
   restart/idempotency and reconciliation evidence in a demo certification
   report.

Only then may a demo certification report ID be used by later live-money
activation gates.

This evidence does not authorize live, PROP, copy-trade or automatic execution.
