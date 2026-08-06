# SignalRankAI v1.5.1 Environment Variables

This file lists the v1.5.1 canonical billing variables that must be reviewed
against the existing Railway configuration. Do not create duplicate aliases
when an equivalent canonical variable already exists.

## Required for web/mobile checkout

```env
APP_NAME=SignalRankAI
APP_BASE_URL=https://app.signalrank.ai
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=
PAYSTACK_CALLBACK_URL=https://app.signalrank.ai/billing/complete
```

`PAYSTACK_CALLBACK_URL` is preferred. When absent, the backend derives
`APP_BASE_URL/billing/complete`.

## Optional Paystack endpoint override

```env
PAYSTACK_BASE_URL=https://api.paystack.co
```

Change this only for an approved compatible Paystack endpoint or controlled
integration test.

## Optional Paystack subscription plan codes

```env
PAYSTACK_PREMIUM_MONTHLY_PLAN_CODE=
PAYSTACK_PREMIUM_QUARTERLY_PLAN_CODE=
PAYSTACK_PREMIUM_YEARLY_PLAN_CODE=
PAYSTACK_VIP_MONTHLY_PLAN_CODE=
```

Backward-compatible tier-wide fallbacks:

```env
PAYSTACK_PREMIUM_PLAN_CODE=
PAYSTACK_VIP_PLAN_CODE=
```

The database product catalogue remains authoritative for price, currency, tier,
and duration. Plan codes do not permit a client to override those values.

## Guarded staging live-payment canary

```env
FULL_SYSTEM_STAGING_TEST_ACTIVE=0
PAYSTACK_LIVE_STAGING_ENABLED=0
PAYSTACK_LIVE_STAGING_ACK=
PAYSTACK_LIVE_STAGING_ALLOWED_CANONICAL_USER_IDS=
PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS=
PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN=56000
```

A canonical-only app account may be allowlisted through
`PAYSTACK_LIVE_STAGING_ALLOWED_CANONICAL_USER_IDS`; a Telegram identity is not
required. This is disabled by default because live keys move real money.

## Receipt email delivery

These existed in the unified account system and are required to deliver actual
receipts rather than leave them queued:

```env
EMAIL_DELIVERY_ENABLED=1
EMAIL_FROM=SignalRankAI <no-reply@signalrank.ai>
EMAIL_MAX_ATTEMPTS=6
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_SSL=0
SMTP_USE_STARTTLS=1
SMTP_TIMEOUT_SECONDS=15
```

## Still disabled by default

```env
REAL_EXECUTION_ENABLED=0
AUTO_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
HYPERLIQUID_MAINNET_EXECUTION_ENABLED=0
REAL_PAYOUTS_ENABLED=0
PAYSTACK_TRANSFERS_ENABLED=0
```

Adding provider, broker, wallet, or payment credentials must not change these
flags automatically.
