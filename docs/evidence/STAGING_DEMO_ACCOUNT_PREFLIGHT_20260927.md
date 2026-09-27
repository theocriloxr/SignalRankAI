# Staging Demo Broker Account Preflight — 2026-09-27

Status: **BLOCKED_EXTERNAL**

Railway deployment: `2d1fa0ed-453e-4ccd-af92-2c2535d79d9b`  
Rollout commit: `2397b5afb8c18226e9545b6391886b03c5d0e3e0`

## Purpose

This preflight answers one narrow question without placing any order or
returning any broker secret:

> Is there already a canonical staging DEMO account that is ready to enter the
> bounded demo-certification workflow?

The answer at the time of this run was **no**. The preflight process exited
non-zero by design because a BLOCKED certification preflight is fail-closed;
Railway therefore labels the short-lived job `CRASHED`, which is expected for
this blocked result and is not a frontdoor/runtime crash.

This latest refresh ran after the MT5 linking-copy safety rollout on frontdoor deployment `33c9b981-29c0-4fef-890f-b314e817a566` / `d09535105bf44...`, which itself followed the explicit safe DEMO-certification preparation workflow
was clean-room certified and deployed to staging frontdoor commit
`e7196d4310180b2e901ab020e7041de7c5e18a91`.
Frontdoor deployment: `713ee164-5002-4499-a7cf-66f67dba0802`.
That release passed Alembic `0045` schema admission, decomposed
`mode=frontdoor` ownership, MetaApi startup probing and `/healthz=200`.
The preparation action performs provider-backed read-only verification and
reconciliation, applies a bounded `DEMO/MANUAL` policy, and deliberately leaves
execution disabled. It cannot place an order or activate live money.

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
