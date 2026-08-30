# SignalRankAI v1.2.6 Certification Report

Date: 2026-07-30
Scope: Telegram callback startup integrity, outcome tracking admission, lifecycle notification recovery, and retention of guarded live-Paystack staging controls.

## Status

**Locally code-certified; Railway runtime proof required.**

## Verified controls

- Runtime banner identifies v1.2.6 independently of stale `APP_VERSION`.
- A partially configured Telegram Application is never exposed to Railway.
- Webhook readiness requires the explicit readiness flag and at least 60 registered handlers.
- Adaptive owner-command import failure cannot abort core callback registration.
- Outcome scans default to the critical DB lane and cannot be configured as background.
- Active-signal reconciliation uses a 12-second bounded DB admission timeout by default.
- Lifecycle event recipients include confirmed, delivered and reconciled delivery proofs.
- Entry/TP notification delivery uses critical DB sessions.
- Existing v1.2.5 live-Paystack guards, adaptive helper, delivery-advisory, rejection telemetry and commodity identity controls remain present.

## Verification results

- Tracked Python compilation: PASS (744 files)
- Schema audit: PASS
- Alembic revisions: 27
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: 8/8 PASS
- DB session API audit: zero legacy calls
- Architecture smoke: PASS
- Secret scan: zero findings
- v1.2.5 compatibility verifier: PASS
- v1.2.6 verifier: PASS
- Focused regression suite: 91 passed, 1 dependency-bound test deselected
- Additional callback/outcome/version regression subset: 34 passed

## Local dependency limitation

The local certification image does not include `python-telegram-bot` or APScheduler. One selected test requiring APScheduler was deselected; Railway logs confirm those declared dependencies are installed in the deployment runtime. Static handler-contract tests and all dependency-independent outcome tests passed.

## Required Railway evidence

1. Startup reports v1.2.6 and a handler readiness count of at least 60.
2. Logs contain `immediate callback ack guard registered`.
3. Every test click produces `callback_ack answered` followed by its concrete callback log.
4. Logs contain `active_scan fetched=` without DB-admission deferral messages.
5. The already delivered signal is reconciled and emits entry/TP notifications as applicable.
6. Delivery proof remains confirmed and notification rows become sent rather than pending/failed.
