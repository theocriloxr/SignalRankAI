# SignalRankAI v1.3.6.7 Integrity, Accounting and Deduplication Hotfix

Date: 2026-08-02
Fingerprint: `v1.3.6.7-integrity-accounting-dedup-hotfix-20260802`
Database head: `0034_production_integrity` — no new migration

## Why this release exists

Runtime evidence from v1.3.6.6 showed four unresolved integrity defects:

1. owner/admin paths could bypass same-user delivery deduplication;
2. near-identical SOL/BTC/BNB theses could be stored and delivered under different IDs;
3. TP1/TP2 protected exits were persisted as `partial_win_be` but often carried `-1R`, leaving `/performance` at `Stopped TP1 / TP2: 0 / 0`;
4. successful terminal notifications were not always globally finalized and could remain in the unnotified queue.

## Fixed

### Signal generation and delivery deduplication

- Added transaction-scoped PostgreSQL locks for both exact thesis fingerprints and semantic `asset/direction/strategy` scopes.
- Added near-entry matching with `SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT`.
- Regime and timeframe no longer split one user-visible thesis by default.
- Removed owner/admin bypasses from delivery reservation and pre-send asset locks.
- Tier-specific cooldown values cannot weaken the global four-hour rule unless two explicit audited flags are enabled.
- Historical duplicate deliveries are excluded from performance claims and duplicate terminal notifications.
- Added a dry-run-first legacy duplicate reconciliation utility.

### TP1/TP2 protected-exit accounting

- Introduced one canonical partial-exit accounting module shared by outcome persistence and performance reconciliation.
- Default plan: close 50% at TP1, 25% at TP2, retain 25% runner.
- A TP1 then breakeven/protected exit now records the weighted realized result, not a full stop.
- A TP2 then breakeven/protected exit includes both planned partial closes.
- Historical `partial_win_be` rows and corresponding ML training labels are repaired by the worker.
- Performance policy upgraded to `proof-ledger-v2-partial-exit` so finalized legacy rows are rebuilt without overwriting explicit human corrections.
- `/performance` now populates `Stopped TP1 / TP2` from canonical lifecycle evidence.

### Outcome notifications

- Terminal messages now include full Signal ID, asset, direction, timeframe, entry, invalidation, observed price/provider, event time, notification time and historical-reconciliation label.
- TP1/TP2 protected exits are labelled separately from stop-before-TP1 losses.
- Outcome stage is resolved before price-evidence fallback.
- Once all non-quiet recipients are delivered or already durably delivered, the outcome is globally finalized.
- Removed recipient-loop throttling from the terminal-notification path and increased the default bounded job budget to 45 seconds.

### Paper recovery

- `/paper_close_all CONFIRM` continues to require live quotes.
- `/paper_close_all FORCE CONFIRM` may use only a recent stored paper mark when a live quote is unavailable.
- Last-mark fallback is bounded by `PAPER_CLOSE_ALL_LAST_MARK_MAX_AGE_SECONDS`.

## Safety boundary

This release fixes source and runtime-integrity defects. It does not certify a 60% win rate, calibrated ML probability, live auto-trading, copy trading, paid launch or public performance marketing. Those remain blocked until the post-deployment runtime gates pass.
