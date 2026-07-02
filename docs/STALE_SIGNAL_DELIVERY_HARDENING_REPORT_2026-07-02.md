# Stale Signal Delivery Hardening Report - 2026-07-02

## Scope

This pass addressed a critical production bug: short-timeframe signals could sit in the queue for hours and still be delivered as if they were actionable. The specific failure pattern was a 5m signal generated at `2026-07-02 01:32 UTC` and delivered with `Freshness: 296m`.

For a 5m setup, that is stale by design. The delivery layer now treats stale signal delivery as a hard rejection condition instead of only displaying freshness in the Telegram message.

## Implemented Changes

### Delivery Freshness Gate

File: `engine/delivery_freshness.py`

- Added a reusable delivery gate that evaluates signal age before Telegram delivery.
- Added timeframe-specific maximum age defaults:
  - `1m`: 2 minutes
  - `3m`: 6 minutes
  - `5m`: 10 minutes
  - `15m`: 20 minutes
  - `30m`: 35 minutes
  - `1h`: 60 minutes
  - `4h`: 180 minutes
  - `1d`: 720 minutes
  - `1w`: 4320 minutes
- Added profile-aware maximum age defaults:
  - `scalp`: 10 minutes
  - `day`: 45 minutes
  - `swing`: 360 minutes
  - `position`: 4320 minutes
- Added opportunity-decay scoring so old signals can be rejected even before the absolute maximum age if too little opportunity remains.
- Added fail-closed live revalidation. By default, if the system cannot obtain a current price for final validation, delivery is blocked instead of sending a potentially stale signal.
- Added execution-time entry drift validation. Signals are rejected when current price has moved too far from the original entry relative to the planned stop distance.
- Added current reward/risk validation. Signals are rejected when live price movement has consumed too much of the reward side before delivery.

### Resend Pipeline Protection

File: `signalrank_telegram/bot.py`

- Added freshness filtering inside the unsent-signal resend job.
- Stale resend candidates are expired through the existing Postgres feature layer where possible.
- The resend pipeline now logs the rejection reason, signal age, maximum allowed age, and remaining opportunity percentage.

### User Delivery Protection

File: `signalrank_telegram/bot.py`

- Added profile-aware freshness validation before a user receives a signal.
- The gate uses the user's configured trade profile when available.
- The old price-only stale validator was replaced by the new full delivery gate:
  - age gate
  - opportunity decay gate
  - current-price revalidation
  - TP/SL already-hit protection

### Final Pre-Send Protection

File: `signalrank_telegram/bot.py`

- Added a final freshness check immediately before a signal is formatted and sent.
- This protects against a signal becoming stale between selection and actual Telegram delivery.

## New Environment Variables

```text
DELIVERY_FRESHNESS_GATE_ENABLED=true
DELIVERY_REQUIRE_LIVE_PRICE=true
DELIVERY_DEFAULT_MAX_SIGNAL_AGE_MINUTES=60
DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT=30
DELIVERY_MAX_ENTRY_DRIFT_STOP_FRACTION=0.75
DELIVERY_MIN_CURRENT_RR=1.0
DELIVERY_MAX_SIGNAL_AGE_BY_TF_MINUTES={"1m":2,"5m":10,"15m":20,"1h":60,"4h":180,"1d":720}
DELIVERY_MAX_SIGNAL_AGE_BY_PROFILE_MINUTES={"scalp":10,"day":45,"swing":360,"position":4320}
```

## Verification

Commands run:

```text
python -m py_compile engine\delivery_freshness.py signalrank_telegram\bot.py
python -m pytest tests\test_delivery_freshness.py tests\test_trader_profiles_and_platform_reliability.py tests\test_deploy_log_regressions.py -q
```

Result:

```text
24 passed, 3 warnings
```

Warnings were pre-existing dependency/deprecation warnings and were not caused by this pass.

## Regression Coverage

File: `tests/test_delivery_freshness.py`

Added coverage proving:

- A 5m signal that is nearly five hours old is rejected.
- Opportunity decay can block late short-timeframe signals.
- Fresh day-profile signals are allowed when enough opportunity remains.
- Live-price validation fails closed when no current price is available.
- Fresh revalidated signals pass when current price data is available.
- Current price drift beyond the configured stop-distance fraction is rejected.
- Current reward/risk below the configured minimum is rejected.

## Current Condition

This removes one of the most trust-damaging production behaviors: stale short-timeframe opportunities reaching users after the market has moved on.

It does not, by itself, prove live Railway delivery latency is fixed. The July 2 logs still showed PostgreSQL pool contention and scheduler pressure, so the next live deploy should confirm:

- stale candidates are logged and expired instead of sent,
- short-timeframe delivered signals show realistic freshness,
- `/db_health` has low wait pressure during active delivery,
- resend jobs no longer push old signals after recovering from DB contention.

## Remaining Production Work

The broader institutional roadmap in the pasted reports remains valid, especially:

- scheduler leader election,
- provider circuit breakers and adaptive scanning,
- portfolio-level risk orchestration,
- full auto-trade lifecycle verification,
- mission-control event timelines,
- long Railway soak testing with real Redis/Postgres/provider keys.

Those are larger production-hardening epics and require live evidence before they can be honestly marked complete.
