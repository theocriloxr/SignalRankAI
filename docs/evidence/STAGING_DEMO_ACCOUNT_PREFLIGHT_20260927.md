# Staging Demo Broker Account Preflight — 2026-09-27

Status: **BLOCKED_EXTERNAL**

Railway deployment: `ad501371-bd3a-431c-8683-701e09c05b4f`  
Rollout commit: `bd94225d37322a280a334dd7286b7c20c5b3b548`

## Purpose

This preflight answers one narrow question without placing any order or
returning any broker secret:

> Is there already a canonical staging DEMO account that is ready to enter the
> bounded demo-certification workflow?

The answer at the time of this run was **no**.

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

1. read-only broker verification must succeed;
2. the account policy must classify the connection as `DEMO`;
3. explicit demo execution permission must be configured;
4. reconciliation must become `HEALTHY`;
5. the account must remain unfrozen and pass all deterministic risk gates;
6. bounded demo order / modify / close / reconciliation evidence must be
   captured through the canonical execution path;
7. the resulting execution/account-ledger evidence must be retained in a demo
   certification report.

Only then may a demo certification report ID be used by later live-money
activation gates.

This evidence does not authorize live, PROP, copy-trade or automatic execution.
