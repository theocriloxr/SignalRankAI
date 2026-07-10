# Interactive + Heavy Background Coexistence Fix — 2026-07-10

## Problem
The bot was delivering signals, but user commands/buttons were slow under load. `/profile_debug` could fail with `NoncriticalWriteDropped`, `/signals` could time out, and the Check Outcome button looked dead while delivery/outcome jobs were active.

## Root cause
Heavy jobs and interactive requests were sharing the same DB session gate. Some interactive paths were using compact signal IDs while the DB query expected full UUIDs. Also the global callback ACK answered buttons immediately, so later handlers that tried to show popup alerts could become invisible to the user.

## Fixes
- Added `interactive=True` DB session priority for user commands/buttons.
- Added a separate background DB gate: `DB_BACKGROUND_MAX_CONCURRENT_SESSIONS`.
- Background jobs can run, but they cannot occupy all DB slots.
- Fixed duplicated `yield` in `db/session.py` session context manager.
- `/profile_debug`, `/signals`, `/db_health`, `open_signal`, and `check_outcome` now use interactive DB sessions.
- Check Outcome now sends a visible reply message instead of relying on a second callback popup.
- Check Outcome and Open Signal now resolve compact signal IDs by prefix.
- `/db_health` now shows interactive and background DB gate metrics.

## Env
Recommended monolith settings:

```env
DB_POOL_SIZE=6
DB_MAX_OVERFLOW=2
DB_MAX_CONCURRENT_SESSIONS=8
DB_INTERACTIVE_SESSION_GATE_TIMEOUT_SECONDS=6
DB_INTERACTIVE_PAUSES_BACKGROUND=1
DB_BACKGROUND_MAX_CONCURRENT_SESSIONS=2
DB_BACKGROUND_SESSION_GATE_TIMEOUT_SECONDS=2
DB_BACKGROUND_DROP_WHEN_BUSY=1
DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE=0
DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT=1
CHECK_OUTCOME_DB_TIMEOUT_SECONDS=6
FREE_RANDOM_DISTRIBUTION_ENABLED=1
SHADOW_OUTCOME_TRACKER_ENABLED=1
OUTCOME_TRACKER_BATCH_SIZE=50
SHADOW_OUTCOME_BATCH_SIZE=50
FREE_RANDOM_DISTRIBUTION_BATCH_SIZE=100
RESEND_UNSENT_INTERVAL_SECONDS=600
```

## Expected logs
- `[callback_ack] answered ...`
- `[check_outcome] user=... ref=... ok=True`
- `/db_health` shows `Background gate: limit=2 ...`
- `/db_health` shows low interactive waiting.
