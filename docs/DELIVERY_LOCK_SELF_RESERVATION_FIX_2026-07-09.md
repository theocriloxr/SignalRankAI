# Delivery Lock Self-Reservation Fix — 2026-07-09

## Problem

Railway logs showed the engine had finally reached a healthy storage state:

- `final_signals > 0`
- `stored=1`
- `store_failed=0`

But Telegram delivery still produced no sends. The sequence was:

1. `record_signal_delivery` created a pending delivery row.
2. `_deliver_or_update_signal_async` checked `_is_asset_delivery_locked` before sending.
3. The lock query counted the same pending delivery row (`sent_ok=False`, `last_error IS NULL`) as an active lock.
4. The bot logged `skipped duplicate asset due to lock` and returned without sending.

That caused `Creating new delivery` followed by `dispatch produced no Telegram sends`.

## Fix

`signalrank_telegram/bot.py` now:

- Excludes the current signal id from asset-lock checks.
- Defaults delivery asset lock to count only successfully sent rows.
- Ignores unsent/pending delivery rows by default.
- Allows owner/admin bypass for delivery verification.
- Lets Railway shorten `ASSET_REPEAT_LOCK_HOURS` during verification instead of forcing 12 hours.
- Logs asset-lock decisions with `require_sent_ok`, `ignore_unsent`, and signal id.

## Required Railway envs

```env
DELIVERY_ASSET_LOCK_REQUIRE_SENT_OK=1
DELIVERY_ASSET_LOCK_IGNORE_UNSENT=1
DELIVERY_ASSET_LOCK_IGNORE_STALE_MINUTES=180
DELIVERY_ASSET_LOCK_FAIL_OPEN_FOR_OWNER=1
OWNER_DELIVERY_BYPASS_ASSET_LOCK=1
ASSET_REPEAT_LOCK_HOURS=2
SIGNAL_COOLDOWN_MINUTES=15
```

## Success marker

Next logs should show:

```text
stored > 0
Creating new delivery: ...
# no skipped duplicate asset due to lock for the same signal
users_dispatched > 0
sent_ok=true
message_id=...
```

Run:

```text
/delivery_debug <signal_ref> <owner_telegram_user_id>
/signal_debug <signal_ref>
/format_debug <signal_ref>
```
