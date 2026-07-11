# Final Storage and Production Wrap-Up Fix — 2026-07-09

## Why this patch exists
The latest Railway logs proved that the market-data and scoring blockers had been solved:

- `crypto_only=True`
- `market_data_assets` reached usable levels
- `strategy_signals` reached 500+
- `max_score` and `max_score_pre_threshold` were populated around 97+
- `final_signals` was positive

The remaining blocker was storage:

- `stored=0`
- `store_failed=final_signals`
- `store_signal failed: TimeoutError`
- DB session gate timeouts were also visible in background consumers.

Without reliable storage, the bot cannot deliver Telegram messages, save `message_id`, or start lifecycle tracking for newly generated signals.

## What changed

### 1. Critical DB lane for signal storage
`db.session.get_session()` now supports:

- `critical=True` for product-critical writes such as `store_signal`
- `noncritical=True` for best-effort writes such as telemetry, resend bootstrap, free distribution, and outcome notification scans

While critical DB work is waiting or active, noncritical calls can drop immediately instead of consuming Railway/PgBouncer connection capacity.

New metrics exposed through pool diagnostics include:

- `critical_waiting`
- `critical_active`
- `noncritical_dropped`

### 2. Store signal uses critical session and a dedicated timeout
`db.pg_compat.store_signal_compat()` now:

- uses `get_session(critical=True)`
- honors `SIGNAL_STORE_TIMEOUT_SECONDS` with default `45`
- retries transient DB failures through `run_with_db_retry`
- logs store timing: `db_wait_ms` and `db_exec_ms`
- logs rich context on failure: asset, direction, timeframe, score, fingerprint, entry, stop loss, TP1, stage, timeout, exception type, and message

### 3. Better engine store failure logging
`engine.core` now logs signal context on storage failure instead of only `store_signal failed`.

### 4. Background jobs can be disabled or skipped during critical storage
New/recognized env flags:

- `SHADOW_OUTCOME_TRACKER_ENABLED=0`
- `SEND_OUTCOME_NOTIFICATIONS_ENABLED=0`
- `FREE_RANDOM_DISTRIBUTION_ENABLED=0`
- `RESEND_SKIP_WHEN_CRITICAL_DB_ACTIVE=1`
- `DB_BACKGROUND_JOBS_SKIP_WHEN_CRITICAL_ACTIVE=1`

These protect the DB gate during engine storage verification.

### 5. Scheduler jobs are staggered
The bot now recognizes the requested startup delay envs:

- `OUTCOME_NOTIFICATION_STARTUP_DELAY_SECONDS`
- `RESEND_UNSENT_STARTUP_DELAY_SECONDS`
- `FREE_DISTRIBUTION_STARTUP_DELAY_SECONDS`

Free distribution is also not scheduled when disabled.

### 6. Worker flag aliases
The worker now recognizes:

- `SHADOW_OUTCOME_TRACKER_ENABLED` as an alias for `WORKER_SHADOW_TRACKER_ENABLED`
- `REALTIME_OUTCOME_TRACKER_ENABLED` as an alias for `WORKER_OUTCOME_TRACKER_ENABLED`

## Verification run in this environment

Passed:

```bash
python -m py_compile engine/core.py db/session.py db/repository.py db/pg_compat.py signalrank_telegram/bot.py worker/worker.py utils/async_runner.py
python -m compileall -q db engine signalrank_telegram worker utils tests/test_storage_priority_hardening.py
python -m pytest tests/test_storage_priority_hardening.py -q
```

Result:

```text
4 passed
```

Focused broad pytest collection was attempted, but this sandbox is missing runtime dependencies such as `python-telegram-bot`, `apscheduler`, and `yfinance`, so unrelated import-collection errors occurred before selected tests could run. This is an environment limitation, not a failure of the patched files.

## Temporary Railway verification envs

Keep crypto-only until storage, delivery proof, and lifecycle notifications are proven.

```env
CRYPTO_ONLY_MODE=1
ASSET_CLASSES_ENABLED=crypto

CRYPTO_MARKET_DATA_PROVIDERS=coinbase,okx,bybit
CRYPTO_PREFERRED_PROVIDER=coinbase

DECISION_LOG_WRITE_ENABLED=0
REJECTION_LOG_WRITE_ENABLED=0
DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT=1
DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE=1
DB_BACKGROUND_JOBS_SKIP_WHEN_CRITICAL_ACTIVE=1

RESEND_UNSENT_INTERVAL_SECONDS=180
RESEND_UNSENT_STARTUP_DELAY_SECONDS=30
OUTCOME_NOTIFICATION_STARTUP_DELAY_SECONDS=90
FREE_DISTRIBUTION_STARTUP_DELAY_SECONDS=150

SIGNAL_STORE_TIMEOUT_SECONDS=45
DB_CRITICAL_SESSION_GATE_TIMEOUT_SECONDS=45
SIGNAL_STORE_RETRY_ATTEMPTS=1

SHADOW_OUTCOME_TRACKER_ENABLED=0
SEND_OUTCOME_NOTIFICATIONS_ENABLED=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
```

## Success markers after deployment

The next healthy Railway log should show:

```text
final_signals > 0
stored > 0
store_failed < final_signals
```

Target:

```text
final_signals=5
stored=5
store_failed=0
```

Then verify Telegram proof:

```text
/delivery_debug <signal_ref> <your_user_id>
```

Expected:

```text
sent_ok=true
chat_id=...
message_id=...
delivery_state=sent
```

After one delivered signal, re-enable lifecycle notifications and verify:

```text
entry_touched
tp1_hit OR sl_hit OR missed_entry OR expired
signal_event_notification sent_ok=True
```

## Re-enable background consumers gradually

After `stored > 0` is stable:

1. Enable resend/delivery first.
2. Enable outcome notifications.
3. Enable realtime lifecycle tracking if disabled.
4. Enable shadow tracker.
5. Enable free distribution.

Do not enable all background DB consumers at once.

## Crypto-only exit rule

Stay crypto-only until the system has at least 12–24 clean hours with:

- `market_data_assets > 0`
- `max_score_pre_threshold` populated
- `stored > 0`
- Telegram `message_id` proof
- at least one lifecycle event notification
- no repeated DB gate timeout storms

Then enable assets in phases:

1. crypto only
2. crypto + FX
3. crypto + FX + commodities
4. crypto + FX + commodities + indices
5. stocks during stock-market hours
