# SignalRankAI Post-Deploy Hardening Report - 2026-07-05

## Scope

This pass addressed the deployed-log failures where OKX returned candles but the
engine reported `market_data_assets=0`, Railway created oversized database pools,
and outcome tracking skipped an authoritative entry/lifecycle state.

## Implemented

### Market data

- OKX is first in the crypto candle and dynamic-discovery order.
- Crypto no longer waits on yfinance before exchange providers by default.
- Timeframes fetch concurrently with separate provider and timeframe deadlines.
- A shared usability validator now requires normalized `timestamp/open/high/low/close/volume`
  candle records and a configurable minimum candle count.
- Engine counters and per-asset gates use that same validator.
- Aggregation logs now report usable and rejected timeframes with exact reasons.
- Optional derivatives/on-chain enrichment runs once per asset, not once per timeframe.

### Database runtime

- Railway defaults are `pool_size=2`, `max_overflow=0`.
- Auxiliary event loops use `NullPool` by default.
- A startup warning is emitted if a Railway monolith requests a pool above five.
- Both `DB_AUXILIARY_NULLPOOL` and the legacy `DB_AUX_LOOPS_USE_NULLPOOL` are accepted.

### Signal lifecycle

- Added `signal_lifecycles` for current persisted state and excursion/timing metrics.
- Added append-only `signal_tracking_events` for generated, entry, TP, SL, BE,
  missed-entry, expiry, and learning events.
- Added `signal_event_notifications` with recipient-level uniqueness.
- TP/SL evaluation is blocked until entry is persisted as touched.
- Entry expiry is `missed_entry`, not a loss.
- TP1 followed by a return to protected stop is `partial_win_be`, not a full loss.
- Immediate event notifications are sent only to confirmed signal recipients.
- Telegram message edits are attempted first; a new event message is sent if edit fails.
- Quiet hours and disabled alert preferences are respected.
- Failed/deferred lifecycle notifications are retried by the realtime tracker.
- The existing outcome notification job remains the fallback path.

### ML outcome quality

- Raw R remains available in metadata.
- Training R is clipped by configurable bounds to prevent extreme bad records from
  dominating training.
- Missing R values no longer cause formatting exceptions.
- Lifecycle events include R, MFE/MAE progression, regime/session, spread, funding,
  order-book imbalance, and open-interest context when available.
- Missed entries and expiries are not trained as losses.

### Timezone and delivery proof

- Added `/timezone` with city aliases, common choices, raw IANA validation, and
  privacy-safe Telegram location resolution.
- Added `/travelmode` and `/settings`, plus profile/settings navigation controls.
- Exact coordinates are discarded unless `TIMEZONE_STORE_LOCATION_COORDINATES=1`.
- Missing timezones are prompted during onboarding and signal-history use without
  blocking the user; Telegram cannot infer a user's timezone automatically.
- Owner/admin users without a configured timezone default to `Africa/Lagos`; others
  default to UTC until configured.
- New signal cards receive recipient-local generated and delivered timestamps.
- Delivery rows persist UTC timestamps, display timezone, rendered local timestamps,
  delivery latency, and signal age at delivery.
- `/delivery_debug` reports local generated/delivered times and age-at-delivery proof.

### Performance baseline v2

- New signals are tagged with `performance_version=2`.
- Existing historical signals remain version 1 and are excluded from v2 performance,
  exposure, fallback, and leaderboard calculations.
- The baseline can be controlled with `PERFORMANCE_BASELINE_VERSION` without deleting
  historical records.
- Training R clipping remains independent from the raw R retained for auditability.

## Migration

Alembic head is `0019_user_timezone_privacy`.

Run on deployment:

```text
python -m alembic -c alembic.ini upgrade head
```

The startup auto-repair path also creates the lifecycle tables and delivery columns
idempotently when startup operations are enabled.

## Railway Variables

```text
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
DB_MAX_CONCURRENT_SESSIONS=4
DB_AUXILIARY_NULLPOOL=1

CRYPTO_PREFERRED_PROVIDER=okx
BINANCE_MARKET_DATA_ENABLED=0
YFINANCE_CRYPTO_PRIMARY_ENABLED=0
USE_MULTI_PROVIDER_DATA=true
MARKET_PROVIDER_TIMEOUT_SECONDS=3
MARKET_TIMEFRAME_FETCH_TIMEOUT_SECONDS=10
MARKET_CACHE_MIN_CANDLES=20
MARKET_ALTERNATIVE_SIGNALS_ENABLED=1
CRYPTO_MICROSTRUCTURE_PROVIDERS=okx,bybit
CRYPTO_DERIVATIVES_PROVIDERS=okx,bybit

OUTCOME_CHECK_INTERVAL_SECONDS=20
OUTCOME_LIFECYCLE_ENABLED=1
LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED=1
SIGNAL_ENTRY_GATING_ENABLED=1
LIFECYCLE_NOTIFICATION_RETRY_LIMIT=100
SIGNAL_TIMEZONE_DISPLAY_ENABLED=1
TRAVEL_TIMEZONE_REFRESH_DAYS=14
TIMEZONE_STORE_LOCATION_COORDINATES=0
TRAINING_R_CLIP_MIN=-5
TRAINING_R_CLIP_MAX=10
PERFORMANCE_BASELINE_VERSION=2
```

For the first deployment containing migrations 0018 and 0019, run Alembic explicitly
or temporarily set `AUTO_MIGRATE=true`. Do not retain old Railway overrides such as
`DB_POOL_SIZE=20` or `DB_MAX_OVERFLOW=20`.

## Verification

- Python compilation passed for all changed Python modules.
- Final timezone, lifecycle, and DB-health regression suite: 30 tests passed.
- Complete suite: 419 tests passed.
- Migration chain is `0018_signal_lifecycle_events` -> `0019_user_timezone_privacy`.
- The local global Python environment did not include the Alembic CLI module, so the
  head command must be run in Railway's installed application environment.

## Post-Deploy Acceptance

1. `/system` and `/db_health` show pool `2/0` and bounded sessions.
2. `/engine_debug` shows `market_data_assets > 0` and no aggregation rejection for
   valid OKX `5m`, `15m`, or `1h` batches.
3. Logs contain `[market_data][aggregation] ... usable=[...]`.
4. A new signal produces a confirmed `/delivery_debug <ref> <user_id>` row with
   chat ID, message ID, local timestamps, and age at delivery.
5. `/timezone Africa/Lagos` updates subsequent card times.
6. `/timezone London`, location sharing, `/travelmode on`, and Settings -> Timezone
   update the saved timezone while UTC remains the storage and calculation standard.
7. `/db_health` reports revision `0019_user_timezone_privacy` and all lifecycle tables.
8. New `/performance` results contain only `performance_version >= 2` signals.
9. Lifecycle logs progress through `entry_touched`, `tp1_hit`, and later terminal state.
10. `signal_event_notifications.sent_ok` becomes true once for each event/recipient.
11. A signal that never touches entry becomes `MISSED_ENTRY`, not `SL_HIT`.

Live provider availability and Telegram acknowledgement still require deployment
verification; local automated tests cannot prove Railway egress or Telegram delivery.
