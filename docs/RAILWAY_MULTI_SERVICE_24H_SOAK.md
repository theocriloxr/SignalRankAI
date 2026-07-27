# Railway multi-service 24-hour soak

## Recommended four-service layout

1. **gateway** — `uvicorn railway_main:app --host 0.0.0.0 --port $PORT`
   Owns health/API, Telegram webhook, commands/callbacks and bot scheduler. Set
   `RUN_ENGINE_LOOP=0` and `RUN_WORKER_LOOP=0`. This is the only public service.
2. **engine** — `python main.py`, `RUN_MODE=engine`,
   `HONOR_RUN_MODE_ON_RAILWAY=true`. Remove its HTTP healthcheck.
3. **worker** — `python main.py`, `RUN_MODE=worker`,
   `HONOR_RUN_MODE_ON_RAILWAY=true`. Owns expiry/maintenance/live outcomes during
   the initial split. Disable ML and shadow ownership here.
4. **analytics** — `python main.py`, `RUN_MODE=analytics`,
   `HONOR_RUN_MODE_ON_RAILWAY=true`. Owns stale/rejected shadow outcomes, bounded
   all-asset candle collection and delayed ML training.

An optional fifth **delivery** service may run the durable receipt reconciler
using `deploy/railway_roles/delivery.env`. It does not replace the engine's
candidate/outbox creation yet, so do not disable the engine delivery-outbox path.

An optional sixth **outcome** service can own live delivered outcomes after
`WORKER_OUTCOME_TRACKER_ENABLED=0` is proven on the worker. Never run both owners.

## Shared resources

All services may share Postgres/PgBouncer and Redis, but use the conservative
2/0 pool in the supplied soak profile. Do not set a Railway HTTP healthcheck on
non-HTTP workers. Keep one gateway replica until singleton bot/scheduler leases
are proven.

## Evidence required after 24 hours

- no DB admission timeout;
- no `Trade opened` before delivery proof;
- stale/rejected rows persisted and later outcome-labelled;
- asset-learning candle counts by class;
- `telegram_send_ok`, `delivery_proof_write`, `active_message_saved`;
- no duplicate delivery;
- no orphan OHLC tasks;
- provider success/failure and circuit summaries;
- one complete WATCHING_ENTRY → ENTRY_TOUCHED → ACTIVE → outcome path.
