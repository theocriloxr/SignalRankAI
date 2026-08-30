# Signal Lifecycle, Monitoring, Tier Access, and Notification Reliability

Status: implementation contract for release validation. The database UUID is
the internal identity; `signals.display_id` is the immutable public identity.

## Dependency and ownership map

| Concern | Authoritative owner | Consumers |
|---|---|---|
| Signal identity | `core.signal_identity`, `db.signal_reference` | formatters, commands, callbacks, diagnostics |
| Global lifecycle | `core.signal_lifecycle`, `engine.signal_lifecycle` | realtime tracker, Monitor, outcome projection |
| Outcome writer | `engine.realtime_outcome_tracker` | outcome outbox, performance, commands |
| Original delivery proof | `db.pg_features.mark_signal_delivery_result` | monitoring, lifecycle recipients, performance |
| Recipient monitoring | `services.user_signal_monitoring` | TP callbacks, lifecycle/outcome suppression, Monitor |
| Effective tier | `db.access.resolve_user_tier` | synchronous Telegram wrapper, delivery authorization |
| Delivery authorization | `services.delivery_authorization` | engine fanout and recovery send paths |
| Outcome outbox | `outcome_notifications`, `db.pg_features` | realtime notification dispatcher |
| Lifecycle outbox | `signal_event_notifications`, `engine.signal_lifecycle` | lifecycle notification dispatcher |
| Engine Pulse | `worker.worker` -> `engine.admin_pulse` | owner/admin Telegram recipients |

The realtime outcome tracker is the only component that advances global market
outcomes. A Monitor refresh is a read projection and cannot advance lifecycle
state. User Continue/Stop actions only update `user_signal_monitoring`.

## Identity and resolver

Every user-visible signal message uses `📌 Signal ID: <display_id>`. New rows
derive the default display ID from the first 12 characters of the UUID and
persist it once. Migration `0030_signal_monitor_reliability` backfills existing
rows and handles a prefix collision by adding a deterministic hash suffix.

The shared resolver accepts a full UUID, display ID, unambiguous legacy UUID
prefix, or Telegram message link. Ambiguous references are rejected. Recipient
lookups require confirmed delivery proof; owner/admin global diagnostics may
resolve without recipient proof.

## Lifecycle and same-candle policy

Terminal states are TP3, Stop Loss, break-even stop, missed entry, and expired.
They cannot transition to another terminal or active state. Lifecycle writes
lock the one signal row, verify the monotonic graph, insert a unique stage
event, and persist terminal event ID/type/price/evidence.

When one OHLC candle spans both a target and Stop Loss and tick order is not
known, the deterministic policy is `stop_loss_first_conservative`. The policy
name is stored in event evidence. This avoids overstating performance.

## Recipient monitoring

Confirmed Telegram delivery creates one `(user_id, signal_id)` monitoring row
in `auto_continue`. TP1 offers Continue to TP2/TP3 or Stop at TP1. TP2 offers
Continue to TP3 or Stop at TP2. No response means monitoring continues.

Callbacks acknowledge immediately, resolve and authorize delivery proof, lock
the recipient state, and record a unique semantic idempotency key. Stop
suppresses later proactive lifecycle/outcome notifications for that recipient
without changing global tracking or other users. `/outcome` and Monitor still
show global truth; Monitor additionally displays the user's monitoring result.
No Continue/Stop keyboard is emitted for terminal outcomes.

## Entitlement order

Effective access is resolved in this order:

1. blocked or suspended -> `none`;
2. current owner-list membership -> `owner`;
3. stored admin role;
4. active paid subscription -> paid tier;
5. otherwise -> `free`.

Owner-list membership is not persisted as the user's paid tier. Removing an
owner override therefore restores the active subscription or Free. Expiry also
returns the user to Free. Completing terms activates normal Free onboarding;
there is no manual owner approval gate.

In normal production, `DELIVERY_AUDIENCE_ALLOWLIST` is diagnostic-only unless
`DELIVERY_AUDIENCE_RESTRICTION_MODE=1` is explicitly set. Staging/testing can
use restriction mode. All tiers retain the same freshness and safety gates.

## Notification outboxes

Both outboxes use claim/send/finalize:

1. atomically change pending/failed (or stale sending) to sending;
2. commit and release the transaction;
3. call Telegram;
4. finalize delivered/failed/suppressed in a new transaction.

Outcome uniqueness is `(signal, recipient, outcome status)`. Lifecycle
uniqueness is `(signal, recipient, event type)`. Claims older than the
configured threshold are recoverable. Failed, blocked, unconfirmed, stopped,
or access-revoked deliveries never become successful outcome notifications.

## Performance accounting

Global outcome statistics use each signal once. User statistics use each
confirmed recipient delivery once and require Telegram chat/message proof.
`net_r` is the sum of signal R values and `avg_r` is the arithmetic mean.
When a user stops at TP1/TP2, that event's R is stored on their monitoring row
and is used instead of a later global TP3/SL result.

## Free queue and Paystack diagnostics

The migration quarantines unsent Free rows already more than 24 hours stale.
The default diagnostic is read-only:

```powershell
python -m scripts.free_signal_queue_diagnostic --stale-hours 24
```

After reviewing counts, quarantine matched rows explicitly with `--apply`.
Quarantine is recoverable by changing selected rows back to `queued`; it does
not delete them. Free random distribution remains environment-specific and is
disabled in production profiles.

When payments are intentionally disabled, missing Paystack secrets are not a
signal-delivery failure. Upgrade links degrade to the existing support route.
When `PAYMENTS_ENABLED=1` or `PAYMENTS_PUBLIC_ENABLED=1`, production readiness
requires valid live public/secret key prefixes; secret values must never be
logged.

## Configuration

- `DELIVERY_AUDIENCE_RESTRICTION_MODE=0` in production, `1` only for a bounded test audience.
- `LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS=300` for stale lifecycle claims.
- `OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS=300` remains the outcome claim threshold.
- `ENGINE_PULSE_DISTRIBUTED_LOCK_ENABLED=1` enables Pulse leader election.
- `ENGINE_PULSE_REQUIRE_DISTRIBUTED_LOCK=1` makes production lock loss fail closed.
- `ENGINE_PULSE_LOCK_TTL_SECONDS=3570` must stay below the hourly interval.

## Deployment and rollback

1. Back up Postgres and verify the current Alembic head.
2. Deploy code and run `python -m alembic upgrade head`; do not stamp over a failed migration.
3. Confirm head `0030_signal_monitor_reliability` and inspect startup readiness.
4. Run the Free queue diagnostic in dry-run mode.
5. Verify one delivered test signal, TP callback, Monitor snapshot, and outbox claim/finalize logs.
6. Confirm exactly one `[engine_pulse_leadership] acquired=true` publisher per interval.

Rollback application code only after disabling new callback traffic. The
migration downgrade removes monitoring history and public display IDs, so take
a backup first. Prefer forward-fixing notification workers; quarantined Free
queue rows can be selectively restored without schema rollback.
