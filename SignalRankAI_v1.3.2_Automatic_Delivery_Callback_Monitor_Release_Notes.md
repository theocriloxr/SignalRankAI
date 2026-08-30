# SignalRankAI v1.3.2 — Automatic Delivery, Callback, and Monitor Recovery

Release fingerprint: `v1.3.2-auto-delivery-callback-monitor-recovery-20260730`

## Incident scope

This release addresses the production behavior reported after v1.3.0/v1.3.1 development:

- users could discover a signal through `/signals` without receiving a durable detailed signal card;
- lifecycle updates could replace the original signal card with a short `Entry Triggered` message;
- JSON-encoded TP arrays were rendered character-by-character;
- Refresh could appear inactive because the visible timestamp changed only once per minute;
- Monitor and Open Signal callbacks depended on stale Telegram message records;
- the fallback Open Signal handler was a no-op;
- monitor cards did not clearly distinguish best observed price from highest TP reached;
- unsent recovery could be skipped while an engine fanout lock was present;
- outcome and lifecycle messages lacked consistent navigation controls.

## Implemented corrections

### Automatic signal delivery

- Keeps new detailed signal cards immutable; lifecycle updates are separate replies.
- Sends primary signal cards and recovery deliveries with Telegram notifications enabled.
- Runs unsent-signal recovery every 30 seconds, beginning 15 seconds after startup.
- Does not suppress recovery merely because the engine fanout lock is active.
- Rotates recovery audiences using the actual recovery interval rather than the obsolete five-minute interval.
- Preserves delivery proof and idempotency before a signal becomes monitorable.

### Automatic outcomes and lifecycle messages

- Parses JSON/list/string TP formats through the canonical price-level parser.
- Uses one canonical TP/SL notification dispatcher to avoid duplicate or out-of-order terminal notices.
- Sends lifecycle updates as non-silent replies to the source signal when Telegram still has it.
- Adds Monitor, Open Signal, and Check Outcome controls to proactive lifecycle alerts.
- Adds the same navigation controls to canonical outcome notifications.
- Runs the outcome notification dispatcher every 30 seconds.

### Inline buttons

- `Open Signal` now renders a fresh, authorized card from PostgreSQL rather than copying a possibly deleted or overwritten Telegram message.
- The global fallback Open Signal handler is functional instead of returning without action.
- Monitor fallback sends a new monitor card and never edits the detailed signal card.
- Failed monitor edits recreate the monitor message and repoint persisted monitor state.
- Every callback receives immediate acknowledgement and visible failure feedback.

### Monitor state and highest price

- Reads `max_price_seen` and `min_price_seen` from lifecycle state.
- Folds a current trusted quote into lifecycle observation during an interactive refresh.
- Displays best observed price and adverse observed price separately from TP progress.
- Infers reached TP levels defensively from the best observed price when event persistence is delayed.
- Uses second-level refresh timestamps so a valid refresh visibly changes the card.
- Refreshes tracked monitor cards every 60 seconds.

## Database and migration status

No new migration is required. The sole Alembic head remains:

`0029_live_financial_ledger`

## Deployment rule

Deploy the complete v1.3.2 archive as a replacement. Do not overlay selected files onto an older release.

Use the v1.3.2 production profile for public signals/subscriptions. Use the separate live-financial activation profile only after broker and payout credentials have been independently verified.
