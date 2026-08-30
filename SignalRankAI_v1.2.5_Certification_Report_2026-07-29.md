# SignalRankAI v1.2.5 Certification Report

Date: 2026-07-29
Scope: log-driven live-Paystack staging, Telegram delivery proof, adaptive imports, rejection telemetry and commodity price identity.

## Status

**Locally code-certified; Railway runtime proof still required.**

The code and archive have been verified without external live API calls. Paystack live checkout, webhook receipt and settlement behaviour require controlled Railway evidence using the operator's sealed live credentials.

## Verified controls

- Runtime banner identifies v1.2.5 code independently of stale `APP_VERSION`.
- Full-system staging requires the original exact acknowledgement.
- Live Paystack staging requires a second exact acknowledgement.
- Live Paystack staging requires live public/secret key prefixes, an allowlisted Telegram user and an amount cap.
- Checkout and webhook mutation share the same policy.
- Live Paystack credentials are never included in source, logs or generated artifacts.
- MT5 live accounts remain disabled and Bybit remains testnet in the staging profile.
- Freshness-advisory Telegram messages are visibly labelled and blocked from auto execution.
- Adaptive root helper imports resolve.
- Rejection-learning singleton and JSON serialization defects are corrected.
- Wrong WTI instrument prices are rejected before scoring/storage.

## Verification results

- Tracked Python compilation: PASS
- Python files checked: 741 before final documentation packaging
- Schema audit: PASS
- Alembic revisions: 27
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: 8/8 PASS
- DB session API audit: zero legacy calls
- Architecture smoke: PASS
- Secret scan: zero findings
- v1.2.5 verifier: PASS
- Focused regression suite: 59 passed
- Full repository collection: blocked locally by missing `python-telegram-bot` and APScheduler packages in the certification container; both packages are declared in the repository requirements and were present in the supplied Railway logs.

## Runtime certification still required

1. Confirm the startup boundary reports `PAYSTACK_LIVE_STAGING_GUARDED` rather than rejection.
2. Initiate one minimum-value owner checkout and verify the amount cap and metadata.
3. Confirm a signed `charge.success` event creates exactly one entitlement mutation.
4. Repeat the same webhook and confirm idempotent handling.
5. Confirm a non-allowlisted Telegram user cannot initialize or apply a live staging payment.
6. Confirm a charge above `PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN` is blocked before Paystack initialization.
7. Confirm at least one Telegram delivery proof reaches `CONFIRMED`.
8. Confirm test-only freshness messages never enter live broker execution.
9. Confirm paper auto-open follows confirmed delivery.
10. Confirm no invalid WTI/commodity instrument price reaches storage.

## Financial warning

Paystack live mode processes real transactions and settlements. Use the smallest practical controlled transaction, keep the allowlist restricted to the owner, and rotate any key suspected of exposure. Never paste secret keys into chat, source files or deployment logs.
