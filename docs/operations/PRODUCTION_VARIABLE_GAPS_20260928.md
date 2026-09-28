# SignalRankAI Production Variable Gap — 2026-09-28

This is a secret-safe inventory. It records variable **presence**, not secret values.

## User input still required

### Transactional email

SignalRank code and sender identity are complete, but the mailbox credential is not present in the production Railway application services.

Required secret:

```env
SMTP_PASSWORD=<password/app-password for hello@criloxsolutions.com>
```

Before enabling delivery, verify that the existing `SMTP_HOST` value is the correct SMTP hostname for the CRILOX/GO54 mailbox. The variable name already exists in Railway, but connected tooling redacts its value, so this repository does not guess it.

The intended non-secret configuration is:

```env
EMAIL_FROM=SignalRankAI <hello@criloxsolutions.com>
EMAIL_REPLY_TO=hello@criloxsolutions.com
SMTP_PORT=587
SMTP_USERNAME=hello@criloxsolutions.com
SMTP_USE_SSL=0
SMTP_USE_STARTTLS=1
SMTP_TIMEOUT_SECONDS=15
EMAIL_MAX_ATTEMPTS=6
```

After the host and password are verified on the delivery-worker service:

```env
EMAIL_DELIVERY_ENABLED=1
```

Then run real verification-email, magic-link, password-reset and payment-receipt canaries and confirm SPF/DKIM/DMARC for the sending domain.

## Already present in production by variable name

The connected production inventory already contains the canonical variables for:

- PostgreSQL runtime and migration URLs;
- state and delivery Redis;
- Telegram bot token, webhook secret and owner identity;
- application auth secret, token pepper and broker-credential encryption key;
- Paystack secret/public keys and callback URL;
- OpenAI key and provider-routing controls;
- Gemini fallback key;
- MetaApi canonical/legacy token names;
- Twelve Data, Polygon, Alpha Vantage, CryptoCompare, CoinGecko, Finnhub and NewsAPI;
- release source/commit gates;
- live-execution / auto-execution / copy-trading / kill-switch controls.

Do not re-enter or rotate those secrets merely because an older branch/document mentions them.

## Optional, not current blockers

These names are absent on the production frontdoor inventory but are not required for the currently deployed product scope:

- `SENTRY_DSN` — optional external error aggregation.
- `TV_WEBHOOK_SECRET` / `TRADINGVIEW_WEBHOOK_SECRET` — required only if the TradingView inbound webhook integration is intentionally enabled.
- `ADMIN_IDS` — optional when no non-owner Telegram administrators are being delegated; owner controls use the configured owner identity.

## Role scoping

Do not copy every secret to every role. Frontdoor-only auth/origin settings do not belong on analytics, and SMTP credentials should be scoped to the delivery worker that drains `email_outbox`. Provider/broker secrets should remain on only the roles that need them.

## Safety

Adding a provider, broker, mailbox or payment credential must never implicitly enable real execution, auto execution, copy trading, payouts or transfers. Those are separate fail-closed activation gates.
