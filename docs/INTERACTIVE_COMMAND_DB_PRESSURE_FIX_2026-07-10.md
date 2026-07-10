# Interactive Command / DB Pressure Fix — 2026-07-10

## Why this patch exists

The latest Railway logs showed that signal delivery was working, but user commands were blocked behind DB-heavy engine/delivery/outcome work:

- `/profile_debug` failed with `NoncriticalWriteDropped: noncritical DB write dropped: critical DB work active`.
- `/signals` hit the command watchdog after 60 seconds.
- `/db_health` showed `Session gate: limit=8 active=4 waiting=11 errors=52`.
- The app still successfully delivered signals and wrote `delivery_proof_write sent_ok=True` / `dispatch_sent_ok`, proving delivery is alive while command responsiveness is the bottleneck.

## What changed

### `signalrank_telegram/bot.py`

- Command audit writes now use `get_session(noncritical=True)` with a short timeout.
- Audit failures are logged as skipped/failed and never block the command handler.
- `/profile_debug` now uses an interactive critical DB read with `PROFILE_DEBUG_DB_TIMEOUT_SECONDS` instead of disposable/noncritical DB access.

### `signalrank_telegram/commands.py`

- Replaced the active `/signals` implementation used by `bot.py` with a bounded interactive query.
- `/signals` now uses `get_session(critical=True)` and `asyncio.wait_for` with `SIGNALS_COMMAND_DB_TIMEOUT_SECONDS`.
- `/signals` returns a compact index and buttons instead of rendering many large signal cards.
- The optional unvoted filter is bounded and skipped if it would delay the command.

### `.env.production.template`

Added command/DB pressure controls:

```env
BOT_COMMAND_AUDIT_TIMEOUT_SECONDS=1
COMMAND_HANDLER_TIMEOUT_SECONDS=25
PROFILE_DEBUG_DB_TIMEOUT_SECONDS=8
SIGNALS_COMMAND_DB_TIMEOUT_SECONDS=6
SIGNALS_COMMAND_LOOKBACK_DAYS=7
SIGNALS_COMMAND_LIMIT=8
FREE_RANDOM_DISTRIBUTION_ENABLED=0
SHADOW_OUTCOME_TRACKER_ENABLED=0
OUTCOME_TRACKER_BATCH_SIZE=50
RESEND_UNSENT_INTERVAL_SECONDS=600
```

## Expected good logs

```text
[bot] bot_events audit skipped/failed: NoncriticalWriteDropped: ...
[profile_debug] user=... profile=... redis_source=DELIVERY_REDIS_URL
[signals_command] fast query timed out ...   # only if DB is truly saturated
```

A skipped audit is acceptable. A command timeout should become rare.

## Why some background features are recommended off in the monolith

The monolith is doing engine scanning, delivery fanout, commands, outcomes, free distribution, shadow tracking, and admin pulse in one process. For real 100k readiness, free distribution and shadow tracking should move to separate worker services. Until then, they should be disabled or heavily throttled during live delivery tests so command responsiveness remains healthy.
