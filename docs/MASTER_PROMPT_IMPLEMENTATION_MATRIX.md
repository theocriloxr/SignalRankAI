# Master Prompt Implementation Matrix — v1.5.0

## Implemented in source

### Trading platform foundation

- Existing multi-service SignalRankAI trading engine and Telegram bot preserved.
- Provider registry and dormant provider configurations.
- Provider-driven instrument persistence and database-universe loader.
- Signal delivery evidence, outcomes, paper trading and portfolio foundations.
- Versioned ML feature, label and dataset contracts.
- Free, Premium, VIP, Professional and Institutional entitlement foundations.

### Unified account ecosystem

- Canonical account shared by Telegram, web, PWA and mobile.
- Existing Telegram-user backfill without creating a separate user store.
- Telegram-to-app activation and app-to-Telegram linking.
- Email/password authentication.
- Email verification.
- Magic-link authentication.
- Password reset.
- TOTP MFA and recovery codes.
- Rotating sessions and device revocation.
- Duplicate identity and merge-review safeguards.

### Web and mobile product

- Responsive authenticated web application and installable PWA.
- Expo Android/iOS source using the same canonical API.
- Signal feed and dynamic market search.
- Paper trading, portfolio and performance views.
- Watchlists, journal, notification preferences and user alerts.
- Profile, billing, security, devices and support views.
- Organization workspaces and invitations.
- Scoped Professional API keys and signed outbound webhooks.

### Security and operations

- HttpOnly cookie sessions and CSRF protection.
- Hashed passwords, login challenges, recovery codes and API keys.
- Encrypted MFA, push and webhook secrets.
- Transactional email outbox.
- Webhook SSRF and replay protections.
- Route-aware rate limits and audit records.
- One-head Alembic chain through `0038_account_security_product`.
- One-owner staging predeploy/bootstrap/certification script.

## Implemented but requiring credentials or runtime infrastructure

- SMTP delivery requires a verified sender and SMTP service.
- Mobile push requires Expo/APNs/FCM credentials.
- Google/Apple OAuth and institutional SSO require external client accounts.
- Paid provider capabilities require keys, plans and permitted data rights.
- Broker connectivity requires safe testnet credentials.
- Paystack production activation requires live keys and webhook verification.

## Runtime evidence still required

- Real staging migration and bootstrap counts.
- Fresh signal generation and confirmed delivery.
- Paper-position opening from that delivery.
- Provider health with the user's configured keys and plans.
- Dependency-complete CI.
- Load, failover and staging-soak evidence.
- Evidence-backed model and strategy performance.

## Not claimable from source code alone

- Guaranteed profitability or a fixed win rate.
- App-store publication.
- Provider licensing approval.
- Legal/regulatory approval.
- Production readiness without staging evidence.
