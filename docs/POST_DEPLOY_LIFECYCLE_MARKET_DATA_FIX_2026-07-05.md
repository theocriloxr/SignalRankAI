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

- Added `/timezone` with IANA timezone validation.
- Owner/admin users without a configured timezone default to `Africa/Lagos`; others
  default to UTC until configured.
- New signal cards receive recipient-local generated and delivered timestamps.
- Delivery rows persist UTC timestamps, display timezone, rendered local timestamps,
  delivery latency, and signal age at delivery.
- `/delivery_debug` reports local generated/delivered times and age-at-delivery proof.

## Migration

Alembic head is `0018_signal_lifecycle_events`.

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
LIFECYCLE_NOTIFICATION_RETRY_LIMIT=100
TRAINING_R_CLIP_MIN=-5
TRAINING_R_CLIP_MAX=10
```

For the first deployment containing migration 0018, either run Alembic explicitly
or temporarily set `AUTO_MIGRATE=true`. Do not retain old Railway overrides such as
`DB_POOL_SIZE=20` or `DB_MAX_OVERFLOW=20`.

## Verification

- Python compilation passed for all changed Python modules.
- Focused regression suite: 38 tests passed.
- Final focused suite after lifecycle additions: 29 tests passed.
- Complete suite: 413 tests passed.
- Alembic reports one head: `0018_signal_lifecycle_events`.

## Post-Deploy Acceptance

1. `/system` and `/db_health` show pool `2/0` and bounded sessions.
2. `/engine_debug` shows `market_data_assets > 0` and no aggregation rejection for
   valid OKX `5m`, `15m`, or `1h` batches.
3. Logs contain `[market_data][aggregation] ... usable=[...]`.
4. A new signal produces a confirmed `/delivery_debug <ref> <user_id>` row with
   chat ID, message ID, local timestamps, and age at delivery.
5. `/timezone Africa/Lagos` updates subsequent card times.
6. Lifecycle logs progress through `entry_touched`, `tp1_hit`, and later terminal state.
7. `signal_event_notifications.sent_ok` becomes true once for each event/recipient.
8. A signal that never touches entry becomes `MISSED_ENTRY`, not `SL_HIT`.

Live provider availability and Telegram acknowledgement still require deployment
verification; local automated tests cannot prove Railway egress or Telegram delivery.
