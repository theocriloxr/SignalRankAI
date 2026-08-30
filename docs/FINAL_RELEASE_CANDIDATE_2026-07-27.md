# SignalRankAI Final Release Candidate Report

**Date:** 2026-07-27  
**Decision:** Continue and harden the current repository; do not rebuild from scratch.  
**Verdict:** `LOCAL_RELEASE_CANDIDATE_CERTIFIED_EXTERNAL_LIVE_GATES_PENDING`

## Why the existing project was retained

The repository already has a coherent modular-monolith architecture, a single Railway process-ownership model, a complete Alembic chain, fail-closed execution/payment gates, declarative Telegram/provider registries, and broad automated coverage. A clean rewrite would discard proven behavior and create more regression risk without resolving external Railway, Telegram, provider, payment, or broker certification requirements.

## Final fixes in this release candidate

1. Preserved queued Telegram updates during webhook registration and explicitly registered message and callback update types.
2. Required a non-empty production `TELEGRAM_WEBHOOK_SECRET` across Railway deployment profiles.
3. Kept Railway activation on `/readyz`, so a process cannot be activated while PostgreSQL, Redis roles, or Telegram readiness are broken.
4. Added a separate migration URL contract for direct PostgreSQL migration access while retaining PgBouncer-compatible runtime access.
5. Made APScheduler interval jobs use explicit `IntervalTrigger` instances, avoiding package-entry-point resolution failures in ZIP/container deployments.
6. Made OpenTelemetry initialization process-wide and idempotent, disabled the console exporter unless explicitly requested, and added explicit tracer shutdown during application teardown.
7. Added a tracer-shutdown idempotency regression test.
8. Added the webhook-secret placeholder to the conservative monolith role profile.
9. Removed a plaintext administrative token from a tracked repository map.
10. Expanded the secret scanner to inspect Markdown, text, and environment documentation and added regression tests proving that leaked assignments are reported without printing the secret value.
11. Regenerated all V7 governance and environment registries after the final source changes.

## Final local certification

The complete system orchestrator ran the full tracked repository in bounded isolated processes.

- System steps: **32 passed, 0 failed**.
- Test files: **151**.
- Tests: **776 passed, 1 skipped, 0 failed**.
- Tracked Python compilation: **pass**.
- Environment contracts: **pass**.
- Alembic graph/schema audit: **pass**, one head (`0022_active_guard_reconcile`).
- Architecture boundary smoke test: **pass**.
- Database session API audit: **pass**.
- Governance freshness and documentation validation: **pass**.
- Repository secret scan: **pass, zero findings**.
- Runtime configuration snapshot: **valid**.
- Railway-like Uvicorn monolith simulation: **pass**.
- `/healthz` request: **pass**.
- Telegram webhook ingress contract: **pass**, queued safely while the bot was intentionally disabled.
- Graceful application shutdown: **pass**, including telemetry shutdown.
- 100,000-user fan-out planner/load contract: **pass**.
- Provider registry and adapter contract certification: **23 providers implemented/mock-verified**.

Evidence is labelled `HERMETIC_LOCAL_ONLY`. It does not falsely represent mocked adapters or local simulation as live provider, Telegram, payment, or broker proof.

## External gates that still require the deployed environment

These cannot be certified from an isolated environment and are not solved by rewriting the code:

1. Railway deployment using the final commit.
2. Direct PostgreSQL migration connection and PgBouncer runtime connection.
3. Separate live RedisState and RedisDelivery services.
4. Telegram network delivery and complete command/button probes.
5. Live/public/sandbox certification for each enabled market-data provider.
6. Paystack test-mode transaction, webhook, receipt, refund, and reconciliation proof.
7. TradingView external alert delivery proof.
8. MetaApi demo account order/modify/close/reconciliation proof.
9. Restart, failover, Redis-loss, and backup/restore drills in staging.
10. A 24–72 hour owner-only soak before public expansion.

Real execution, public payments, payouts, copy trading, and unrestricted distribution remain fail-closed until their independent evidence gates pass.

## Mandatory Railway configuration corrections

Before deploying this release candidate:

- Generate and seal a new `TELEGRAM_WEBHOOK_SECRET`.
- Rotate every credential that appeared in the uploaded plaintext environment export.
- Use one numeric value for `OWNER_TELEGRAM_ID`; keep multiple values only in `OWNER_IDS`.
- Remove malformed packed variables such as `B_POOL_SIZE` and define each variable separately.
- Remove shell substitutions from Railway variable values.
- Set `AUTO_EXECUTION_ENABLED=0` and `BYBIT_EXECUTION_ENABLED=0` until demo execution certification passes.
- Keep the engine off for initial command recovery, then activate owner-only crypto REST after `/readyz` and command/button probes are clean.

## Recommended next action

Deploy this exact source archive to a fresh Railway staging environment, rotate credentials, apply the corrected owner-beta profile, run `scripts/telegram_webhook_recovery.py`, run runtime deployment diagnostics, and begin the owner-only soak. Do not activate every product line simultaneously.
