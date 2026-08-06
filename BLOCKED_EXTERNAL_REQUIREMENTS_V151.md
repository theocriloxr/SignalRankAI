# SignalRankAI v1.5.1 — External Completion Requirements

These requirements cannot be truthfully completed or proven inside a source
archive. They require access to real infrastructure, credentials, contracts,
market activity, or third-party review.

> Deployment remediation update: repository-side automation for the staging
> database migration, shared database reference, ordered service upload and log
> evidence is now included in `scripts/railway_finish_staging.ps1`. Running that
> command still requires the owner's authenticated Railway session and therefore
> remains an external action.

## Railway and database

- Access to the user's Railway staging and production projects.
- Push the exact release commit to the branch used by all services.
- Apply `0038_account_security_product` to the real staging PostgreSQL database
  through exactly one migration owner.
- Run tier, entitlement, provider, and instrument bootstrap against staging.
- Confirm all services report the same exact 40-character commit SHA.
- Capture deployment IDs, readiness results, and rollback evidence.

## Messaging and identity providers

- Real staging and production Telegram tokens and webhook ownership.
- A verified SMTP or transactional-email account.
- SPF, DKIM, and DMARC configuration for the sending domain.
- Google and Apple OAuth clients.
- Institutional SSO metadata where offered.

## Market-data and execution providers

- Provider API keys and paid plans where required.
- Confirmation of external-display and redistribution permissions.
- OANDA or another authoritative FX/metals bid-ask source.
- Alpaca, Massive, or another authoritative U.S. equity quote source.
- Safe testnet credentials for any execution venue.
- Mainnet execution remains separately gated and is not approved by this file.

## Payments

- Paystack staging/live keys owned by the user.
- Registered and verified Paystack webhook URL.
- A real app-created canonical-user checkout test.
- A real Telegram-linked checkout test.
- Verified webhook activation, durable receipt creation, and receipt-email
  delivery in staging.
- Merchant, tax, refund, and subscription terms approved by the business.

## Mobile distribution

- Expo/EAS project ownership.
- APNs and FCM credentials.
- Apple and Google developer accounts.
- Signing certificates, provisioning profiles, privacy declarations, store
  screenshots, review submissions, and publication.

## Legal and compliance

- Jurisdiction-specific review of signals, financial promotions, subscriptions,
  copy trading, broker linking, portfolio functionality, and execution.
- Privacy, data-retention, cookie, marketing-consent, and deletion policies.
- Provider terms and exchange restrictions.
- Approval of public performance and marketing claims.

## Trading-performance evidence

Source code cannot prove a 60–75% win rate. Required evidence includes:

- Point-in-time, leakage-free data.
- Walk-forward and purged validation.
- Realistic spreads, fees, slippage, funding, and entry-fill treatment.
- Adequate sample sizes per segment.
- Shadow and paper evidence across multiple regimes.
- Immutable delivered-signal and outcome lineage.
- Coverage reported alongside accuracy.

## Required staging certification

Before production promotion, capture all of the following:

1. All three services on one exact release SHA.
2. PostgreSQL at `0038_account_security_product`.
3. Readiness passing with no schema mismatch.
4. Non-zero products, prices, entitlements, provider mappings, and instruments.
5. Engine logging `universe_source=database_registry`.
6. Existing Telegram users retaining subscriptions and trading history.
7. App-created users linking Telegram without duplicate canonical accounts.
8. Email verification, magic login, reset, TOTP MFA, and device revocation.
9. App-only Paystack checkout using a server-resolved product price.
10. Paystack webhook activation and durable receipt delivery.
11. One fresh post-deployment signal with confirmed Telegram delivery proof.
12. One eligible paper position opened from that confirmed delivery.
13. No duplicate delivery or duplicate paper position.
14. Trusted quote sources for each enabled public asset class.
15. A clean staging soak of at least 24 hours.
16. Load, failover, backup, restore, and incident-response evidence.

Live execution, transfers, and payouts must stay disabled throughout this
certification unless a separate explicit safety and legal approval is completed.
