# SignalRankAI v1.2.6 — Callback and Outcome Recovery

Date: 2026-07-30

## Incident addressed

The v1.2.4 Railway log showed a partially initialised Telegram application. `run_bot()` failed while importing `engine.adaptive.helpers`, but Railway accepted an Application object containing only a subset of handlers. Telegram callback updates reached the webhook and returned HTTP 200, yet no callback ACK or route executed.

The same log showed the real-time outcome tracker starting but repeatedly failing to fetch active delivered signals because its database work was classified as discardable background work. Consequently entry, TP1 and later lifecycle transitions were not recorded or notified.

## Changes

- Webhook Application exposure is transactional: Railway receives the app only after the full handler contract is registered.
- Railway requires both the explicit handler-ready flag and the configured minimum handler count.
- Partial applications are rejected instead of silently returning HTTP 200 for ignored buttons.
- Adaptive owner command imports are isolated so an optional module cannot remove core callback routes.
- The callback ACK guard and callback routes remain part of the required readiness contract.
- Outcome active-signal and reconciliation queries now use a critical/interactive database lane with a bounded admission timeout.
- Outcome scans emit positive evidence (`active_scan fetched=...` and `reconciliation_backfill fetched=...`).
- Lifecycle event notification recipient matching normalises `confirmed`, `delivered` and `reconciled` delivery states.
- Lifecycle notification DB operations use the critical lane.
- Existing delivered signals are reconciled after restart, allowing missed entry/TP milestones to be recorded when the current market observation still proves them.

## Safety

Live Paystack staging remains guarded by the v1.2.5 second acknowledgement, owner allowlist and amount cap. MT5 live accounts remain disabled in the staging profile and Bybit remains testnet.

## Database

No migration was added. Alembic head remains `0027_launch_paper_trading`.
