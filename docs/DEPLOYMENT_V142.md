# SignalRankAI v1.4.2 Deployment Runbook

## Staging first

1. Back up the staging database.
2. Stop or scale down application services.
3. Configure exactly one migration owner with a direct
   `DATABASE_MIGRATION_URL`.
4. Run `scripts/staging_predeploy_v142.sh`.
5. Verify `python -m alembic heads` and `current` both report
   `0037_unified_product_workspaces`.
6. Deploy worker, engine, then front door from the same commit.
7. Verify `/healthz`, `/readyz`, `/app`, the platform capabilities endpoint and
   the staging Telegram bot.
8. Run one honest fresh-signal/delivery/paper certification and a 24-hour soak.

## Railway variables

Copy the relevant values from `.env.example` and `.env.providers.example`.
Do not add aliases when a canonical variable already exists. Provider adapters
without credentials must remain `missing_credentials`, not crash the service.

## Bootstrap

The bootstrap is idempotent:

```bash
python -m tools.bootstrap_ecosystem
python -m tools.bootstrap_ecosystem --discover --top 100
```

Discovery is opt-in during predeploy because public providers can be rate-limited.
Recurring discovery is owned by the worker after startup.

## Safety defaults

Keep real execution, auto execution, copy trading, mainnet execution, transfers
and real payouts disabled until a separate execution certification is approved.
