# SignalRankAI v1.3.6.8 Release Notes

## Status

Staging candidate. Production certification remains blocked until runtime logs pass the included checklist.

## Fixed

- Isolated each user performance projection with a nested database savepoint.
- Added full per-user reconciliation diagnostics and grouped failure codes.
- Added explicit all-users-failed certification failure.
- Preserved committed partial-exit repairs before surfacing ledger batch failure.
- Replaced repeat-first-page behavior with a resumable internal-user cursor.
- Added durable failed-user retry state and a bounded operator-visible dead-letter list.
- Persisted reconciliation checkpoints only after the database commit succeeds.
- Aligned legacy delivery-proof timestamp fallback across batch selection and per-user projection.
- Calculated projection coverage from distinct user-signal delivery scopes rather than retry/attempt rows.
- Added an explicit canonical outcome-to-ledger mismatch gate and mismatch samples to `/performance_audit`.
- Added audited system policy migration for finalized ledger rows.
- Preserved human corrections.
- Added bounded dry-run/apply/status owner rebuild operations and ledger audit command.

## Added, disabled by default

- Partitioned durable Redis Streams event transport with consumer groups, ACK, stale reclaim and DLQ.
- Universal provider capability contracts and certification states.
- 100,000+ user architecture, threat, capacity, release, rollback and certification plan.
- Railway v1.3.6.8 staging variables template.

## Safety

- No new database migration.
- No live execution, copy trading, Hyperliquid or provider execution flag enabled.
- Existing integrity triggers remain active.
- Public performance claims remain disabled.
