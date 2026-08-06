# SignalRankAI v1.5.0 External Completion Requirements

The archive intentionally does not contain, fabricate or claim completion of:

- Railway project access, deployment IDs or environment mutation.
- Real PostgreSQL/Redis credentials or a migration run against those services.
- SMTP credentials and a verified sending domain with SPF, DKIM and DMARC.
- Google/Apple OAuth clients, institutional SSO metadata or production domains.
- Provider API keys, paid subscriptions or market-data redistribution licences.
- Telegram bot tokens or proof of webhook ownership.
- Paystack production keys or verified production webhook delivery.
- Expo, APNs or FCM credentials.
- Apple/Google developer accounts and signing certificates.
- App Store or Play Store review and publication.
- Broker/exchange testnet or live trade credentials.
- Legal/regulatory approval for advice, signals, copy trading or execution.
- Statistically valid evidence for a 60–75% win-rate claim.
- A fresh staging signal, confirmed delivery, paper-position opening and soak.

## Required staging evidence

Before production promotion, capture:

1. All services running the same exact commit.
2. PostgreSQL at `0038_account_security_product`.
3. Non-zero tier, entitlement, provider and instrument bootstrap counts.
4. Successful email verification, magic login, reset and TOTP MFA flows.
5. Existing Telegram users retaining subscriptions and trading history.
6. App-created users linking Telegram without duplicate canonical users.
7. One fresh signal delivered with a stored Telegram message ID.
8. One eligible paper position opened from a confirmed delivery.
9. No duplicate delivery or paper position.
10. Dependency-complete tests and a clean staging soak.

Live execution and payouts must stay disabled throughout this certification.
