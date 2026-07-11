# Delivery / DB Contention Activation Fix — 2026-07-10

## Why this patch exists

Railway logs proved the bot could generate, store, and deliver at least one real signal, but after that first successful delivery window the engine repeatedly hit `deliver_all failed TimeoutError`, `store_signal failed TimeoutError`, and DB session-gate pressure.

The root cause was not strategy logic anymore. Delivery was still treated as one large blocking batch, while outcome/background jobs used normal DB sessions and competed with signal storage and Telegram proof writes.

## What changed

### `engine/core.py`

- Bounded each per-user dispatch inside `deliver_all()` using `DELIVERY_USER_TIMEOUT_SECONDS`.
- Reduced the outer `DELIVER_ALL_TIMEOUT_SECONDS` default from 180 seconds to 60 seconds.
- Added delivery skip reasons for per-user timeouts/errors.
- Added operator asset blacklist enforcement before cycle queue refresh.
- Added a pipeline-level blacklist guard so blacklisted symbols cannot re-enter later.

### `signalrank_telegram/bot.py`

- Added bounded Telegram send timeout via `TELEGRAM_SEND_TIMEOUT_SECONDS`.
- Added bounded delivery send timeout via `DELIVERY_SEND_TIMEOUT_SECONDS`.
- Added bounded delivery reservation timeout via `DELIVERY_RESERVE_TIMEOUT_SECONDS`.
- Added bounded per-signal fallback reservation timeout via `DELIVERY_RESERVE_ONE_TIMEOUT_SECONDS`.
- Added bounded delivery proof DB write via `DELIVERY_PROOF_TIMEOUT_SECONDS`.
- Made delivery proof writes use critical DB priority because proof rows must be saved after Telegram accepts a message.
- Disabled live signal edit/update lookup by default with `DELIVERY_SIGNAL_UPDATE_ENABLED=0` to prevent extra DB work during first launch.
- Made active-message tracking and VIP webhook work best-effort/noncritical so Telegram delivery can return quickly.
- Added a bounded asset-lock pre-send check with fail-open on timeout.
- Added freshness-gate timeout controls so delivery does not hang on live-price checks.

### Outcome/background DB sessions

These files now use noncritical DB sessions where appropriate:

- `engine/realtime_outcome_tracker.py`
- `engine/shadow_outcome_worker.py`
- `worker/worker.py`
- `worker/market_monitor.py`
- `engine/signal_monitor.py`

When signal storage or delivery proof writes are critical-active, these background jobs can drop/skip instead of consuming the Railway connection budget.

## New env variables

```env
DELIVER_ALL_TIMEOUT_SECONDS=45
DELIVERY_USER_TIMEOUT_SECONDS=18
DELIVERY_RESERVE_TIMEOUT_SECONDS=8
DELIVERY_RESERVE_ONE_TIMEOUT_SECONDS=8
DELIVERY_SEND_TIMEOUT_SECONDS=12
DELIVERY_PROOF_TIMEOUT_SECONDS=10
TELEGRAM_SEND_TIMEOUT_SECONDS=10
TELEGRAM_EDIT_TIMEOUT_SECONDS=8
DELIVERY_ASSET_LOCK_TIMEOUT_SECONDS=2
DELIVERY_FRESHNESS_TIMEOUT_SECONDS=4
DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN=1
DELIVERY_FRESHNESS_ERROR_FAIL_OPEN=1
DELIVERY_SIGNAL_UPDATE_ENABLED=0
VIP_WEBHOOK_DISPATCH_ENABLED=0
ASSET_BLACKLIST=USDTARS,USDTIDR,DOGEIDR,DXY,VIX,US10Y,US02Y,US500,NAS100,US30
```

## Activation envs

```env
WORKER_OUTCOME_TRACKER_ENABLED=1
REALTIME_OUTCOME_TRACKER_ENABLED=1
ENGINE_OUTCOME_TRACKER_ENABLED=0
SEND_OUTCOME_NOTIFICATIONS_ENABLED=1
SHADOW_OUTCOME_TRACKER_ENABLED=1
FREE_RANDOM_DISTRIBUTION_ENABLED=1
```

## Success markers

Look for:

```text
stored > 0
store_failed=0
users_dispatched > 0
sent_ok=true
telegram_message_id=...
deliver_all failed does not repeat
DB session gate timeout does not storm
```
