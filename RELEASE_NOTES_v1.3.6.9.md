# SignalRankAI v1.3.6.9 — Outcome Delivery Recovery Hotfix

Date: 2026-08-03
Release fingerprint: `v1.3.6.9-outcome-delivery-recovery-hotfix-20260803`
Target: controlled staging only
Migration head: `0034_production_integrity` (unchanged)

## Why this release exists

The v1.3.6.8 worker detected TP/SL events but repeatedly failed to persist them with:

```text
[outcome_tracker] persist_outcome error: name '_env_bool' is not defined
```

The supplied worker capture contains 137 occurrences. `list_delivery_recipients_for_signal()` referenced `_env_bool()` even though `db/pg_features.py` did not define it. Because outcome persistence and recipient-outbox creation shared one transaction, this notification-layer exception rolled back the Outcome row and prevented the front door from finding anything to send.

## Corrections

- Restored a defensive `_env_bool()` helper in `db/pg_features.py`.
- Commits canonical Outcome and signal terminal state before attempting notification fan-out.
- Isolates outbox failure in a later transaction; a Telegram/outbox problem can no longer erase terminal trading evidence.
- Adds traceback-rich outcome persistence logging with full signal/status context.
- Repairs both missing Outcome rows and stale pending/lifecycle-disagreement rows.
- Uses one nested transaction/savepoint per signal and per outbox repair item.
- Preserves human/audited corrections and attributes any system correction.
- Recreates missing notification outbox rows idempotently for recent closed outcomes.
- Adds user-facing terminal messages for protected exits, expiry/time-stop, missed entry and invalidation.
- Adds notification-cycle metrics: pending outcomes, recipients, sent, failed, quiet-hour deferrals and elapsed time.
- Adds Redis-backed resend budget backoff so the resend loop does not compete every scheduler tick after exhausting its budget.
- Adds strict-owner commands:
  - `/outcome_rebuild dry_run`
  - `/outcome_rebuild apply`
  - `/outcome_rebuild status`
  - `/outcome_audit [days]`

## Validation completed locally

- v1.3.6.9 static verifier: passed.
- Full package Python compilation: passed.
- Hotfix/integrity regression group: 131 passed.
- Additional outcome-focused group: 69 passed, 3 dependency-import tests deselected because this sandbox cannot install the declared Telegram/APScheduler packages.

Local tests are not production certification. Railway staging must prove outcome persistence, outbox drainage and exactly-once delivery with real PostgreSQL, Redis and Telegram.

## Deployment verdict

Deploy this release to staging after a database backup. Keep all real execution, copy trading, public payments and public performance marketing disabled. Do not approve production until the gates in `SignalRankAI_v1.3.6.9_DEPLOYMENT_AND_CERTIFICATION.md` pass.
