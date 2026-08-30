# Master Prompt Implementation Matrix — v1.5.1

This matrix maps the combined SignalRankAI prompts to the current source
archive. “Implemented” means code and local tests exist. “External evidence”
means completion depends on the user's infrastructure, credentials, licences,
market activity, or third-party approval.

## Trading intelligence and engine

| Requirement | Status | Notes |
|---|---|---|
| Multi-asset signal engine | Implemented | Crypto, FX, equity, commodity and index architecture retained; public delivery still depends on certified providers. |
| Strategy registry | Implemented foundation | Versioned status, capability and certification contracts; strategies must be activated only when implemented and tested. |
| Expanded strategy families | Implemented foundation/ongoing evidence | Trend, momentum, mean reversion, breakout, price action, ICT/SMC, Wyckoff, Fibonacci, harmonics, derivatives, statistical and macro contracts are represented; public certification remains evidence-based. |
| Regime-aware strategy selection | Implemented foundation | Strategy and regime metadata, adaptive selection and quarantine paths retained. |
| Canonical signal geometry | Implemented | Direction, entry, stop, targets and R:R validation paths retained. |
| Lifecycle correctness | Implemented | Pending-entry, active, terminal, pre-entry invalidation, MFE/MAE and outcome states retained. |
| Delivery evidence and deduplication | Implemented | Durable attempts, receipts, freshness checks and paper eligibility retained. |
| Paper trading | Implemented | Canonical user/account foundations, risk fields and lifecycle retained. |
| Portfolio risk | Implemented foundation | Portfolio, exposure and performance APIs exist; live connected-account evidence is external. |
| Guarded execution | Safety foundations only | Credentials do not enable execution; testnet/live certification and legal approval remain external. |

## Machine learning and performance integrity

| Requirement | Status | Notes |
|---|---|---|
| Versioned dataset/features/labels | Implemented | Explicit dataset, feature and label contracts retained. |
| Leakage-aware validation | Implemented foundation | Time-series governance and promotion gates retained. |
| Class-imbalance metrics | Implemented | Majority baseline, balanced accuracy, positive recall/F1, MCC, PR-AUC, calibration and expected-R gates. |
| Champion/challenger governance | Implemented | Rejected candidates cannot silently replace the champion. |
| Drift detection | Implemented | Feature drift is measured; real resolution and model certification require runtime datasets. |
| 60–75% validated win rate | External evidence | No guarantee is hardcoded; requires statistically valid segmented evidence. |
| Immutable verified performance | Implemented foundation | Delivery/outcome lineage and correction records retained; public certification requires staging/live evidence. |

## Providers and instruments

| Requirement | Status | Notes |
|---|---|---|
| Provider registry | Implemented | Public, credentialed, disabled, degraded and missing-credential states. |
| Dormant adapters | Implemented foundation | Provider configuration and activation contracts; real capabilities require credentials/plans. |
| Dynamic provider discovery | Implemented | Instrument persistence, provider mappings and discovery jobs. |
| Database-backed universe | Implemented | Engine loader supports registry as authoritative source and fail-closed certification. |
| Dynamic asset search | Implemented | Web/API/Telegram foundations use canonical instruments. |
| Provider SDK dependency groups | Implemented | Optional provider/runtime packages and environment guides retained. |
| Trusted FX/metals/equity quotes | External configuration | Requires OANDA/Alpaca/Massive or equivalent valid accounts and licences. |
| Data redistribution rights | External approval | Cannot be granted by source code. |

## Unified identity and account system

| Requirement | Status | Notes |
|---|---|---|
| One canonical user | Implemented | Telegram, web, mobile, API and organizations reference canonical users. |
| Existing Telegram migration | Implemented | Backfill and merge-review foundations preserve history. |
| Telegram-to-app activation | Implemented | Hashed, single-use, expiring activation challenge. |
| App-to-Telegram linking | Implemented | One-time link code and conflict handling. |
| Duplicate-account merge review | Implemented | No name-only destructive merge. |
| Email/password | Implemented | Modern hashing and password policy. |
| Email verification | Implemented | Transactional challenge and outbox. |
| Magic link | Implemented | Enumeration-safe request flow. |
| Password recovery | Implemented | Expiring challenge and session revocation. |
| TOTP MFA/recovery codes | Implemented | Encrypted secret, replay control and hashed one-use codes. |
| Passkey/OAuth/SSO | Foundations/external | Client credentials and platform integration require external accounts. |
| Devices and session revocation | Implemented | Rotating session family and user controls. |

## Web, PWA and mobile product

| Requirement | Status | Notes |
|---|---|---|
| Responsive web application | Implemented | Real canonical API integration, not numeric-ID login. |
| Installable PWA | Implemented | Manifest/service-worker and safe caching rules. |
| Android/iOS shared source | Implemented | Expo/React Native source with secure API/session flows. |
| Signal feed and monitor | Implemented foundation | Runtime data depends on staging engine and WebSocket/event configuration. |
| Dynamic market explorer | Implemented | Canonical instrument search and filters. |
| Paper/portfolio/performance | Implemented | Application APIs and screens. |
| Journal/watchlists/alerts | Implemented | Durable user records and APIs. |
| Profile/security/devices | Implemented | Cross-channel account and security controls. |
| Support tickets/conversations | Implemented | User and administration foundations. |
| Push notifications | Implemented foundation | Expo/APNs/FCM credentials and delivery evidence are external. |
| App Store/Play Store publication | External | Requires signing accounts and review. |

## Tiering, billing and growth

| Requirement | Status | Notes |
|---|---|---|
| Five customer tiers | Implemented | Free, Premium, VIP, Professional, Institutional. |
| Roles separate from tiers | Implemented | Owner/admin/support/etc. do not become customer tiers. |
| Central entitlements | Implemented | Server-side feature, quota and channel enforcement foundations. |
| Existing Premium/VIP plans | Implemented | Server catalogue retains configured products and prices. |
| Canonical app-only checkout | Implemented in v1.5.1 | Web/mobile user can subscribe without Telegram. |
| Server-authoritative pricing | Implemented in v1.5.1 | Client cannot submit amount, tier or duration. |
| Paystack webhook activation | Implemented | Canonical or Telegram-linked activation, idempotent events. |
| Durable receipts and email | Implemented in v1.5.1 | Receipt storage and transactional email queue. |
| Trials/promotions/referrals | Implemented foundation | Real campaign and payout operations require business configuration. |
| Affiliate/ambassador system | Implemented foundation | Fraud and approval contracts retained; real payouts are external. |
| Professional API keys | Implemented | Scoped and hashed keys. |
| Signed webhooks | Implemented | Encrypted secret, SSRF protection, retries and delivery records. |
| Organizations/institutional workspaces | Implemented foundation | Membership, invitations, roles and tenant controls. |
| Business analytics | Implemented foundation | Event records and key funnels; real metrics require deployed traffic. |

## Security and operations

| Requirement | Status | Notes |
|---|---|---|
| HttpOnly sessions and CSRF | Implemented | Secure web session pattern retained. |
| Secret encryption | Implemented | MFA, push and webhook secrets protected. |
| SSRF/replay/idempotency | Implemented | Webhook and payment safeguards. |
| Route-aware rate limiting | Implemented | Authentication, app and professional API limits separated. |
| Security/audit events | Implemented | Durable account and sensitive-operation evidence. |
| One Alembic head | Implemented | `0038_account_security_product`. |
| One migration owner tooling | Implemented | `scripts/staging_predeploy_v151.sh`. |
| Deterministic complete CI | Implemented | 20 bounded pytest batches and full system orchestrator. |
| Local secret scan | Passed | Zero findings in final local certification. |
| Railway simulation | Passed locally | Real application entrypoint, optional local-only dependency stubs. |
| Backup/restore and disaster drill | External runtime evidence | Requires the real Railway database and storage. |
| 24-hour staging soak | External runtime evidence | Requires deployed services and live configured providers. |

## Local final evidence

```text
Release: 1.5.1
Alembic head: 0038_account_security_product
Tests: 1344 passed
Optional environment-dependent skip: 1
Secret findings: 0
```

## Items not claimable from this archive

- Railway deployment or environment mutation.
- Real provider health without the user's credentials and plans.
- Real Paystack settlement or receipt delivery.
- App-store publication.
- Legal/regulatory approval.
- Guaranteed profitability or a fixed win rate.
- Production readiness without staging and soak evidence.
