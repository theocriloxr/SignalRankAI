# SignalRankAI v1.5.1 Staging Deployment Guide

## Release invariants

- Version: `1.5.1`
- Sole Alembic head: `0038_account_security_product`
- One migration owner only
- Worker → engine → front door deployment order
- Live execution, transfers, and payouts disabled

## 1. Back up staging

Create and verify a staging PostgreSQL backup before migration. Confirm that the
staging Redis, Telegram bot, webhook, Paystack configuration, OAuth clients,
and provider credentials are isolated from production.

## 2. Configure the migration owner

Only one Railway service should run the migration/bootstrap predeploy step.
Provide a direct PostgreSQL migration URL, not a transaction-pooling URL.

```env
DATABASE_MIGRATION_URL=<direct staging PostgreSQL URL>
EXPECTED_ALEMBIC_HEAD=0038_account_security_product
APP_ENV=staging
APP_VERSION=1.5.1
EXPECTED_RELEASE_COMMIT=<exact 40-character commit SHA>
```

Run:

```bash
scripts/staging_predeploy_v151.sh
```

The script must fail if there is more than one Alembic head, migration does not
reach `0038_account_security_product`, or bootstrap/certification fails.

## 3. Required safety values

```env
REAL_EXECUTION_ENABLED=0
AUTO_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
HYPERLIQUID_MAINNET_EXECUTION_ENABLED=0
REAL_PAYOUTS_ENABLED=0
PAYSTACK_TRANSFERS_ENABLED=0
```

Credentials alone must not alter these values.

## 4. Deploy services

```text
1. SignalRankAI worker/delivery
2. striking-optimism engine
3. bountiful-miracle front door
```

All services must report the same exact commit SHA and schema head.

## 5. Bootstrap and verify

Verify non-zero counts for:

- subscription products
- subscription prices
- entitlements
- provider registry
- canonical instruments
- provider-instrument mappings
- certified or analysis-ready instruments

The engine must report:

```text
universe_source=database_registry
```

Static asset fallback must remain disabled during certification.

## 6. Identity and application tests

Validate:

- existing Telegram user opens `/app` and retains all data
- app-created user links Telegram
- duplicate account enters merge review rather than destructive merge
- email verification
- magic login
- password reset
- TOTP MFA and recovery code
- device/session revocation
- web/PWA and mobile clients use the same canonical data

## 7. Payment tests

Use an approved staging canary only:

- list server-priced products
- app-only canonical user checkout
- Telegram-linked user checkout
- signed Paystack webhook
- canonical subscription activation
- entitlement update
- durable receipt
- receipt email
- no client amount accepted

## 8. Trading certification

Capture one naturally qualified post-deployment signal with:

- valid geometry
- certified instrument and strategy
- trusted fresh quote
- confirmed Telegram delivery
- stored message ID and delivery proof
- eligible paper-position opening after entry
- no duplicate delivery or position

Do not lower quality thresholds to manufacture certification evidence.

## 9. Soak and promotion

Run at least 24 hours of staging soak. Production promotion remains blocked
until schema, identity, billing, provider, delivery, paper, security, load,
backup/restore, and compliance evidence all pass.
