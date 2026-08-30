# SignalRankAI v1.5.0 Staging Deployment

## Release scope

This release completes account recovery, email verification, TOTP MFA,
expanded web/mobile product views, portfolio/performance APIs, workspace
invitations, support conversations, notification records, user alerts and the
unified account foundation introduced in v1.4.2.

## Migration chain

The sole expected head is:

```text
0038_account_security_product
```

The shortened revision identifiers fit Alembic's common `VARCHAR(32)` version
column. Do not stamp the database without running the migrations.

## Safe staging order

1. Back up staging PostgreSQL.
2. Stop the front door, engine and worker.
3. Configure `DATABASE_MIGRATION_URL` on one migration owner only.
4. Run `scripts/staging_predeploy_v150.sh`.
5. Verify tier, provider, instrument and model bootstrap diagnostics.
6. Deploy worker, engine and front door from the same commit/archive.
7. Verify `/healthz` and `/readyz` separately.
8. Test account registration, email delivery, verification, MFA and recovery.
9. Test Telegram activation and app-to-Telegram linking without duplicate users.
10. Complete a fresh signal → confirmed delivery → paper-position test.
11. Run a clean staging soak before production promotion.

## Required account variables

```env
APP_VERSION=1.5.0
APP_BASE_URL=https://staging-app.example.com
APP_AUTH_SECRET=
ENCRYPTION_KEY=
EMAIL_DELIVERY_ENABLED=1
EMAIL_FROM=
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_SSL=0
SMTP_USE_STARTTLS=1
```

Retain all execution and payout kill switches during staging.
