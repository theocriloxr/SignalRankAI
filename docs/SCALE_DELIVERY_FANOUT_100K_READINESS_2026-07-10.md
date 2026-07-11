# Scale Delivery Fanout / 100k Readiness Patch — 2026-07-10

## Why this patch exists
The latest logs showed the app starts cleanly, webhook is active, blacklist enforcement works, and the engine can fetch market data. However, delivery and background workers can still compete with the engine. For 100k users, the engine must not wait on Telegram fanout.

## Important platform limit
Telegram default bot broadcast throughput is about 30 messages/second. A 100,000-user broadcast cannot be instant with the free broadcast path. At 25–30 msg/s it takes about 55–67 minutes. Telegram paid broadcasts can raise throughput to about 1000 msg/s when `allow_paid_broadcast=True`, but this costs Telegram Stars.

## Changes
- Added `submit_background_coro()` to `utils/async_runner.py`.
- Engine now schedules `deliver_all()` in background when `ENGINE_DELIVERY_ASYNC_FANOUT=1`.
- Engine uses a short fanout lock so multiple delivery fanouts do not stack on every scan cycle.
- Telegram send guard now has a true process-wide rate limiter using `TELEGRAM_BROADCAST_RPS`.
- Telegram send guard can pass `allow_paid_broadcast=True` when `TELEGRAM_ALLOW_PAID_BROADCAST=1`; older PTB versions automatically retry without this argument.
- Redis state/delivery traffic can use `DELIVERY_REDIS_URL` or `STATE_REDIS_URL`, leaving `REDIS_URL` for webhook intake.

## Recommended activation envs

### Normal safe broadcast mode
```env
ENGINE_DELIVERY_ASYNC_FANOUT=1
ENGINE_DELIVERY_FANOUT_LOCK_SECONDS=90
TELEGRAM_BROADCAST_RPS=25
TELEGRAM_GLOBAL_SEND_DELAY_SECONDS=0
TELEGRAM_ALLOW_PAID_BROADCAST=0
TELEGRAM_SEND_MAX_ATTEMPTS=3
TELEGRAM_RETRY_AFTER_MAX_SECONDS=60
```

### Paid broadcast stress mode
Only enable if the Telegram bot account has enough Stars and you accept the cost.
```env
TELEGRAM_ALLOW_PAID_BROADCAST=1
TELEGRAM_BROADCAST_RPS=750
```

### Second Redis
Keep `REDIS_URL` for webhook intake. Add one of these for state/delivery traffic:
```env
DELIVERY_REDIS_URL=redis://...
# or
STATE_REDIS_URL=redis://...
```

### DB pool
Do not simply set DB_POOL_SIZE=100. PgBouncer multiplexes clients but PostgreSQL still has a finite backend connection budget.

Start with:
```env
DB_POOL_SIZE=4
DB_MAX_OVERFLOW=2
DB_MAX_CONCURRENT_SESSIONS=6
DB_POOL_DISABLE_RAILWAY_CAP=0
DB_POOL_ALLOW_UNCAPPED_RAILWAY=0
```

Only after confirming `SHOW max_connections;` and PgBouncer capacity, use:
```env
DB_POOL_DISABLE_RAILWAY_CAP=1
DB_POOL_ALLOW_UNCAPPED_RAILWAY=1
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=4
DB_MAX_CONCURRENT_SESSIONS=12
```

## Success markers
Logs should show:
```text
[engine] delivery fanout scheduled background=true
asset blacklist removed=...
stored > 0
store_failed=0
sent_ok=true
telegram_message_id=...
```

## Red flags
```text
deliver_all failed TimeoutError
store_signal failed TimeoutError
Timed out waiting for DB session gate
telegram flood control retry storms
```

## 100k reality check
For 100k users, production should eventually split into services:
1. Engine service — scans markets and stores signals.
2. Delivery fanout worker(s) — sends Telegram messages through a shared Redis queue.
3. Outcome worker — tracks TP/SL/expired states.
4. Command/webhook service — answers users quickly.
5. Metrics/admin service — dashboards and audits.

This patch makes the monolith safer and faster, but true 100k simultaneous delivery requires horizontal fanout workers and Telegram paid broadcasts or a slower, rate-limited campaign.
