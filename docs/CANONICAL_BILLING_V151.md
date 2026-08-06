# Canonical Billing and Paystack Integration — v1.5.1

## Design rule

Telegram, web, and mobile use one canonical SignalRankAI user and one product
catalogue. A client is never allowed to determine the amount charged.

## Checkout flow

```text
Authenticated canonical user
→ select subscription product ID
→ backend loads active product and current price from PostgreSQL
→ backend validates account, verified email, currency, and product availability
→ backend initializes Paystack with server-resolved amount
→ Paystack metadata records canonical user ID and resolved product details
→ user completes checkout
→ signed webhook is verified
→ webhook re-resolves the product catalogue
→ payment event is persisted idempotently
→ canonical subscription and entitlements are activated
→ durable receipt is stored
→ verified-email receipt is queued
→ Telegram confirmation is sent only when a linked Telegram identity exists
```

## Security invariants

- No client-supplied amount.
- No client-supplied tier or duration.
- Callback URL comes from trusted server configuration.
- Paystack authorization URL must be HTTPS and hosted by Paystack.
- Payment references and webhook processing are idempotent.
- Canonical user and Telegram identity mismatches fail closed.
- App-only users can subscribe without Telegram.
- Adding payment credentials does not enable payouts or execution.

## API

```text
GET  /api/v1/platform/billing/products
POST /api/v1/platform/billing/checkout
GET  /api/v1/platform/billing
```

The checkout request contains a product identifier and optional supported
currency only. Product price and entitlement effects are returned from the
server catalogue.

## Contact-sales products

Professional or Institutional products without a positive active price are
not initialized through self-service Paystack checkout. They return a
contact-sales state and require an approved contract/pricing workflow.

## Staging canary

Staging live-payment testing remains opt-in. Allowlisting can use canonical user
IDs through:

```env
PAYSTACK_LIVE_STAGING_ALLOWED_CANONICAL_USER_IDS=
```

Telegram allowlists remain supported for linked accounts. Production payment
activation requires separate merchant and webhook verification.
