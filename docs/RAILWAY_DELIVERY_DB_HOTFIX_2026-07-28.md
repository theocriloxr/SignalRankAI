# Railway Delivery and DB Hotfix — 2026-07-28

SignalRankAI v1.0.6 repairs the delivery failures proven by the first live
staging engine cycles. The engine generated and stored valid signals, but a
five-user sequential fanout took 152–276 seconds. Later recipients reached the
freshness gate after the queue budget expired, and some durable delivery-state
writes timed out behind the single critical DB lane.

## Runtime repairs

- Alembic revision `0024_ml_rejected_delivery` adds
  `ml_rejected_signals.signal_id` plus its index.
- Clean-schema and auto-ops paths create the same column.
- Delivery reservation, validation, SENDING, proof, and failure writes use the
  user-facing interactive admission lane instead of competing with signal
  storage and lifecycle work in the critical lane.
- Asset-lock checks reuse the open reservation transaction; they no longer
  acquire a nested session.
- Engine-originated batches carry a profile-verification proof, avoiding a
  second DB profile read after the engine has already filtered the signals.
- Per-user signal dictionaries are copied before profile/price annotations, so
  metadata cannot leak across recipients.
- The primary `OWNER_TELEGRAM_ID` is delivered first.
- `DELIVERY_AUDIENCE_ALLOWLIST` supports a staging-only proof audience.
- The engine fanout lock defaults to 600 seconds, uses a unique ownership token,
  and is compare-and-delete released when fanout finishes.
- The resend scheduler yields while engine fanout is active.
- Outcome polling uses the deferrable background lane and retries on its next
  interval instead of starving delivery.
- Failed deployment static checks print their output tail for diagnosis.

## Safety properties retained

Delivery remains fail-closed. Telegram I/O cannot begin unless the durable
phase transition commits, and a delivery is counted only after Telegram proof
is stored. Duplicate evidence failure still blocks delivery rather than sending
blindly.

## Staging proof configuration

Set the following temporarily while validating one account:

```env
APP_VERSION=1.0.6
DELIVERY_AUDIENCE_ALLOWLIST=<PRIMARY_OWNER_TELEGRAM_ID>
ENGINE_DELIVERY_FANOUT_LOCK_SECONDS=600
RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE=1
```

Remove `DELIVERY_AUDIENCE_ALLOWLIST` after the single-user proof succeeds and
then expand the audience gradually.
