# SignalRankAI v1.2.5 — Live Paystack, Delivery, Adaptive and Telemetry Hotfix

Release date: 2026-07-29
Release fingerprint: `v1.2.5-live-paystack-delivery-adaptive-telemetry-20260729`
Database migration head: `0027_launch_paper_trading` (unchanged)

## Evidence from the v1.2.4 Railway run

The v1.2.4 deployment correctly entered acknowledged full-system staging mode and generated/stored signals. Across the supplied log window it stored 11 signals and opened 11 internal tracked trades. Telegram delivery still returned zero because final freshness checks rejected every owner candidate. The log also exposed:

- guarded staging disabled Paystack because live keys were supplied;
- a hybrid root-level adaptive component imported `engine.adaptive.helpers`, which did not exist;
- shadow rejection learning called `persist_rejection` on the wrong singleton;
- nested datetimes in rejection features were not JSON serializable;
- WTI was generated from an invalid `3.535` instrument price and later compared with a live crude-oil price near `84.30`.

## Changes

### Guarded Paystack LIVE staging

Paystack live keys can now be exercised in Railway staging only when all controls are present:

- full-system staging acknowledgement is valid;
- `PAYSTACK_LIVE_STAGING_ENABLED=1`;
- the exact second acknowledgement is configured;
- both live key prefixes are present;
- the Telegram user is allowlisted;
- the transaction amount is positive and does not exceed the configured NGN cap.

Production behaviour is not rewritten. Test keys continue to work in non-production without the live-mode acknowledgement.

Checkout initialization and webhook entitlement mutation use the same policy. Metadata includes `amount_ngn`, key mode and guarded-staging status. Webhook HMAC verification checks the canonical Paystack secret key and an optional rotation fallback without logging either value.

### Staging delivery proof without live execution

For allowlisted full-system staging users, a failed final freshness check may be delivered as an explicitly labelled test message:

`TEST ONLY — NOT EXECUTION ELIGIBLE`

The message includes the freshness reason and is tagged as excluded from production performance. Automatic/live broker execution is hard-blocked for these advisory messages. Production delivery remains fail-closed.

This allows Telegram receipt proof, delivery persistence, paper auto-open, monitoring, callback and outcome paths to be exercised even when a free provider is temporarily rate-limited or cannot quote an asset.

### Adaptive compatibility

Added `engine/adaptive/helpers.py`, which re-exports the canonical component helper functions. This makes clean and stale-overlay deployments compatible with both root and component import paths.

### Rejection learning

- `engine.rejection_learning` now uses the `MLRejectionTracker` singleton rather than `SignalDeduplicator`.
- Rejection feature payloads are recursively converted to JSON-safe values before spool insertion.
- Datetimes, tuples, sets, non-finite floats and arbitrary objects no longer crash batch persistence.

### Commodity identity sanity

Broad instrument-specific ranges now reject obviously wrong provider identities for WTI, Brent, gold, silver and natural gas. The same validation is applied to yfinance, cache and provider-waterfall payloads before engine diagnostics and scoring.

### Diagnostics and environment contracts

- Deployment diagnostics recognise test-key mode and guarded live-Paystack staging separately.
- The environment validator accepts acknowledged staging integration profiles while retaining the hard block on live MT5 accounts.
- v1.2.5 staging and production profiles are included in deployment diagnostics.

## Required staging settings

```env
APP_ENV=staging
FULL_SYSTEM_STAGING_TEST_MODE=1
FULL_SYSTEM_STAGING_TEST_ACK=I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS
FULL_SYSTEM_TEST_USER_IDS=1409578077
DELIVERY_AUDIENCE_ALLOWLIST=1409578077

PAYMENTS_ENABLED=1
PAYMENTS_PUBLIC_ENABLED=1
PAYMENTS_PUBLIC_TEST_MODE=0
REAL_PAYOUTS_ENABLED=1
PAYSTACK_LIVE_STAGING_ENABLED=1
PAYSTACK_LIVE_STAGING_ACK=I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY
PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS=1409578077
PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN=56000
PAYSTACK_SECRET_KEY=<stored only in Railway>
PAYSTACK_PUBLIC_KEY=<stored only in Railway>

STAGING_DELIVERY_FRESHNESS_ADVISORY=1
STAGING_TEST_DELIVERY_LIVE_EXECUTION_BLOCK=1
MT5_ALLOW_LIVE_ACCOUNTS=0
BYBIT_TESTNET=1
```

No credentials are included in the release archive.

## Expected Railway evidence

Startup:

```text
[boot] SignalRankAI v1.2.5
release=v1.2.5-live-paystack-delivery-adaptive-telemetry-20260729
[startup_safety] requested=1 acknowledgement_valid=1 full_system_test_enabled=1 environment=staging
PAYSTACK_LIVE_STAGING_GUARDED
[worker] AdaptiveCandleCapture started
[worker] PaperTradingWorker started
```

Signal and delivery:

```text
final_signals=<greater than 0>
stored=<greater than 0>
[dispatch] staging freshness advisory retained ... live_execution_blocked=1
delivery_proof_write ... state=CONFIRMED
[paper_auto_open] ...
```

The following must no longer appear:

```text
No module named 'engine.adaptive.helpers'
'SignalDeduplicator' object has no attribute 'persist_rejection'
Object of type datetime is not JSON serializable
GHOST PRICE ... WTI ... 3.535
PAYSTACK_LIVE_KEY_REJECTED
```
