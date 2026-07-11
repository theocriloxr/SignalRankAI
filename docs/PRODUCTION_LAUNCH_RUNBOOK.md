# Production Launch Runbook

Last updated: 2026-06-29
Owner: Engineering/Ops

This runbook is the operational checklist for public production launch with real
paying customers. It records what can be verified from the codebase and what must
be validated in the deployment environment.

## Pre-Launch Gates

1. Run project-owned compile check excluding `.venv`, `.git`, `__pycache__`, and `.pytest_cache`.
2. Run full regression suite: `.venv/Scripts/python.exe -m pytest -q`.
3. Run governance check: `.venv/Scripts/python.exe scripts/validate_governance_docs.py`.
4. Run offline readiness check: `.venv/Scripts/python.exe scripts/production_readiness_check.py`.
5. Verify `/health`, `/healthz`, and `/metrics/prometheus` in the deployed web process.
6. Verify first admin pulse after deploy shows non-zero scanned evidence when DB has recent `signals`, `decision_log`, or `signal_deliveries`.
7. Verify no duplicate risk-free updates are sent for the same user/asset/direction/timeframe cooldown window.
8. Verify market-data logs show real candle providers filling OHLCV data, with no demo/synthetic candle generation.
9. Verify weekly admin report includes non-zero Redis shadow counters when shadow tracking has activity.
10. Verify `/ops_health` from an admin Telegram account.
11. Verify Telegram sandbox command/callback workflow before public webhook routing.
12. Verify payment sandbox upgrade and webhook reconciliation.
13. Confirm production secrets are set in the hosting provider, not committed files.
14. Confirm migration plan, backup plan, and rollback owner.
15. Update `docs/PRODUCTION_READINESS_SCORECARD.md` with final evidence.

## Launch Sequence

1. Freeze risky feature changes.
2. Apply migrations against production database.
3. Deploy web/API process.
4. Verify web health and metrics.
5. Deploy worker/engine process.
6. Verify provider health and engine logs.
7. Deploy or switch Telegram webhook.
8. Send sandbox/admin smoke commands.
9. Enable payment flow.
10. Monitor metrics, logs, delivery failures, and user onboarding.

## Rollback

- If web health fails: route traffic back to previous release or disable public route.
- If worker misbehaves: stop worker process and keep web/payment paths online.
- If Telegram sends fail or spam: disable webhook/polling and pause outbound delivery.
- If payment reconciliation fails: pause paid upgrade prompts and reconcile manually.
- If market-data provider degrades: disable affected provider and use fallback routing.
- If migration fails: stop write traffic and follow DB restore/forward-fix plan.

## Incident Contacts

| Role | Responsibility |
| --- | --- |
| Engineering owner | Release decision, rollback, code fixes |
| Ops owner | Hosting, env vars, logs, metrics, backup/restore |
| Product owner | Customer messaging and pricing/entitlement decisions |

## Evidence To Capture

- Test command and result.
- Deployment version or commit identifier where available.
- Health endpoint responses.
- Metrics endpoint reachability.
- Telegram admin smoke result.
- Payment sandbox result.
- Any accepted launch risks with owner and expiry.
