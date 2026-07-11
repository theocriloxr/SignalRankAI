# Living Deployment Register

Last updated: 2026-06-29
Owner: Engineering/Ops

This register tracks deployment topology, release controls, validation gates,
rollback paths, operational dependencies, and readiness evidence.

| Area | Current Evidence | Required Control | Health Checks | Rollback | Status | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime entrypoints | `main.py`, `railway_main.py`, `run_server.py`, `Procfile`, `start.sh`, `railway.json` exist. | Keep web/bot/worker modes explicit and documented. | `/health`, `/healthz`, `/metrics/prometheus`, `/ops_health` | Revert release, restore previous env profile. | Partial | Engineering |
| Migrations | `alembic`, manual migrations, and auto-op safeguards exist. | Run migrations before traffic shift; disable unsafe auto-migration for public launch unless explicitly accepted. | DB `SELECT 1`, migration head check | Restore DB backup or forward-fix migration. | Partial | Engineering |
| Secrets | `.env.example`, `.env.production.template`, Railway prefill script exist. | No secrets committed; rotate production secrets before launch. | Startup env readiness check, `/ops_health` | Revoke/rotate compromised token. | Open | Engineering/Ops |
| Health and metrics | FastAPI health and Prometheus metrics exist. | Add alerting and dashboard ownership. | `/health`, `/healthz`, `/metrics/prometheus` | Route traffic away or pause worker/bot. | Partial | Engineering/Ops |
| Telegram bot | Webhook/polling registration and `/ops_health` exist. | Sandbox E2E test before public launch. | `/ops_health`, webhook readiness logs | Disable webhook, pause outbound sends. | Partial | Engineering |
| Payments | Paystack/webhook modules exist. | Verify signature validation and payment journey in sandbox. | Payment webhook smoke test | Manual entitlement reconciliation. | Partial | Engineering/Ops |
| Market/news providers | Provider health tracking and circuit breaker helpers exist. | Provider failover and outage playbook. | Provider status command, provider health metrics | Disable provider and degrade safely. | Partial | Engineering |
| Backups/DR | Not fully documented in code evidence. | Define backup schedule, restore drill, RPO/RTO. | Restore drill evidence | Restore latest verified backup. | Open | Engineering/Ops |

## Release Checklist

- Full test suite passes.
- Governance validation passes: `python scripts/validate_governance_docs.py`.
- Offline production readiness passes: `python scripts/production_readiness_check.py` with real-data contract checks.
- Project-owned compile check passes excluding `.venv`, `.git`, caches.
- Health endpoints return acceptable responses in target environment.
- Metrics endpoint is reachable by monitoring.
- Telegram sandbox E2E passes or is explicitly accepted as deferred.
- Payment sandbox flow passes or is explicitly accepted as deferred.
- Migration/rollback plan is reviewed.
- Production readiness scorecard is updated.
