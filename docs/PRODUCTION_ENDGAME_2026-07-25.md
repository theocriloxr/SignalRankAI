# SignalRankAI production endgame

## What the 25 July Railway log proved

HTTP health, Redis, the Telegram webhook, market-data retrieval, strategy generation and durable signal storage all work. The stored LINKUSDT row proves the candidate pipeline reaches Postgres.

The deployment was not production-safe because it ran `PUBLIC_TESTING_MODE=1`, enabled analytics in the monolith, trained on synthetic bootstrap rows after the live DB read was deferred, counted undelivered rows as portfolio exposure, and treated Redis emptiness as permission to expire database rows.

## Required Railway deployment

Use `bash start.sh` as the start command and set `PUBLIC_TESTING_MODE=0` in every live service.

Recommended services:

1. Gateway: `deploy/railway_roles/gateway.env`; attach the public domain and `/healthz` health check.
2. Engine: `deploy/railway_roles/engine.env`; no HTTP health check.
3. Worker: `deploy/railway_roles/worker.env`; no HTTP health check.
4. Outcome: `deploy/railway_roles/outcome.env`; no HTTP health check.
5. Analytics: `deploy/railway_roles/analytics.env`; start only after live delivery proof is visible.

For a temporary single-service owner beta, use `deploy/railway_roles/monolith_safe.env`. Do not enable ML, drift monitoring or shadow learning there.

## Acceptance gate

Keep auto-execution disabled until a 24-hour owner-only soak proves, for the same signal ID: a `signals` row, `signal_deliveries.sent_ok=true`, Telegram chat/message IDs, active-message persistence, lifecycle `WATCHING_FOR_ENTRY`, entry touch when applicable, and a proof-eligible terminal outcome.

## ML rule

Production training now requires at least 100 delivery-proof-backed live outcomes by default, even when shadow/archive rows are also available. Synthetic bootstrap data is local/test-only and can no longer overwrite the Railway model.
