# Delivery, Profile, and Second Redis Observability Fix — 2026-07-10

## Why this patch exists

The bot can now start, scan, store signals, and schedule background delivery fanout, but the logs did not clearly prove every final step:

- which Redis was used for state/delivery locks,
- whether the second Redis was actually active,
- which user trader profile was applied,
- whether Telegram send started,
- whether Telegram returned a message id,
- whether the message id was persisted to `signal_deliveries`,
- whether `ActiveSignalMessage` was saved for lifecycle/edit tracking.

This patch adds explicit proof logs and a `/profile_debug` command so the next Railway logs are easy to diagnose.

## Files changed

- `core/redis_state.py`
- `engine/core.py`
- `signalrank_telegram/bot.py`
- `utils/async_runner.py`
- `.env.production.template`
- `docs/DELIVERY_PROFILE_REDIS_OBSERVABILITY_FIX_2026-07-10.md`

## New proof logs

Expected Redis/state logs:

```text
[redis_state] connected source=DELIVERY_REDIS_URL url=redis://***@... separate_delivery=True separate_state=True fallback_to_main=False
[engine] delivery fanout scheduled background=true candidates=... ttl=90s redis_source=DELIVERY_REDIS_URL separate_delivery=True connected=True
```

Expected profile logs:

```text
[engine_profile_load] user=... tier=... profile=... risk=... assets=... sessions=... execution=...
[profile_apply] user=... tier=... trade_profile=... risk=... candidates_before=...
[profile_apply_result] user=... profile=... candidates_after=... dropped=...
```

Expected Telegram delivery logs:

```text
[delivery_reserve_ok] user=... signal=... asset=... tf=... tier=... profile=...
[delivery_attempt_start] user=... signal=... asset=... tf=... display_tier=... profile=...
[delivery_format_ok] user=... signal=... asset=... tf=... text_len=...
[delivery_telegram_send_begin] user=... signal=... timeout=...
[telegram_send_start] chat=... attempt=... text_len=... rps=... paid=...
[telegram_send_ok] chat=... message_id=... elapsed_ms=...
[send_signal_ok] user=... signal=... chat_id=... message_id=...
[active_message_saved] user=... signal=... chat_id=... message_id=...
[delivery_telegram_send_ok] user=... signal=... chat_id=... message_id=...
[delivery_proof_write] user=... signal=... sent_ok=True chat_id=... message_id=... state=sent error=None
[dispatch_sent_ok] user=... signal=... asset=... tier=... profile=... sent_count=...
```

If Telegram delivery still fails, the log should now show the exact failure point:

```text
[delivery_format_empty]
[telegram_send_timeout]
[telegram_send_error]
[active_message_save_failed]
[delivery_proof_write] sent_ok=False
[delivery] proof write timeout
```

## New command

Run:

```text
/profile_debug
```

It returns:

- saved trading profile,
- risk profile,
- asset classes,
- sessions,
- notification style,
- execution mode,
- resolved profile constraints,
- active Redis source,
- whether separate delivery Redis is active.

## Recommended verification envs

```env
DELIVERY_TRACE_ENABLED=1
TELEGRAM_SEND_SUCCESS_LOG_ENABLED=1
ENGINE_DELIVERY_ASYNC_FANOUT=1
ENGINE_DELIVERY_FANOUT_LOCK_SECONDS=90
TELEGRAM_BROADCAST_RPS=25
TELEGRAM_ALLOW_PAID_BROADCAST=0
TELEGRAM_SEND_MAX_ATTEMPTS=3
TELEGRAM_SEND_TIMEOUT_SECONDS=20
DELIVERY_SEND_TIMEOUT_SECONDS=25
DELIVERY_PROOF_TIMEOUT_SECONDS=15
DELIVERY_PREFS_TIMEOUT_SECONDS=3
```

Second Redis:

```env
REDIS_URL=<main webhook Redis private URL>
DELIVERY_REDIS_URL=<second Redis private URL>
STATE_REDIS_URL=<second Redis private URL>
```

DB with PgBouncer for stress testing:

```env
DB_POOL_SIZE=6
DB_MAX_OVERFLOW=2
DB_MAX_CONCURRENT_SESSIONS=8
DB_POOL_SIZE_RAILWAY=6
DB_MAX_OVERFLOW_RAILWAY=2
DB_POOL_DISABLE_RAILWAY_CAP=1
DB_POOL_ALLOW_UNCAPPED_RAILWAY=1
```

## 100k note

This improves architecture and observability, but true 100,000-user simultaneous delivery still depends on Telegram throughput. Free bot broadcast throughput is limited; paid broadcast mode is required for near-real-time mass fanout.
