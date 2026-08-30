# SignalRankAI v1.3.6 Railway Performance Decomposition

Date: 2026-08-02  
Release fingerprint: `v1.3.6-railway-performance-decomposition-20260802`  
Migration head: `0033_ml_learning_runtime`

## Objective

Move SignalRankAI from the Railway `RUN_MODE=all` monolith into a safe first-stage three-service topology to reduce command latency and database/event-loop contention without changing signal logic or enabling unrestricted financial execution.

## Runtime evidence that triggered this release

The latest v1.3.5 staging deployment successfully reached migration head `0033_ml_learning_runtime`, registered the Telegram webhook and started all major subsystems. The attempted environment-only split then showed the front-door process with a webhook database role while still logging both `Engine loop task created` and `Worker loop task created`. It also retained a reviewed `12+4` monolith pool. This proved that environment variables alone did not establish reliable process ownership.

## Implemented changes

### 1. First-class `frontdoor` role

`runtime/roles.py` now models `frontdoor` explicitly. It owns:

- FastAPI ingress and readiness routes;
- Telegram webhook, commands and callbacks;
- bot scheduler and delivery/retry work.

It does not own the signal engine or legacy worker loop. `webhook` and `front-door` remain accepted compatibility aliases.

### 2. Source-enforced ownership

`railway_main.py` resolves and logs a fail-closed process ownership contract. In `frontdoor` mode:

- stale `RUN_ENGINE_LOOP=1` is ignored;
- stale `RUN_WORKER_LOOP=1` is ignored;
- the engine and worker cannot be restarted by background monitors;
- `railway_main:app` rejects dedicated engine/worker modes using the wrong start command.

`DECOMPOSED_TOPOLOGY_ENABLED=1` rejects `RUN_MODE=all` and unknown-role monolith fallback.

### 3. Dedicated entrypoints

`start.sh` now routes:

- `frontdoor` to one Uvicorn worker serving `railway_main:app`;
- `engine` to the dedicated signal engine through `main.py`;
- `worker` to the existing full background worker compatibility path.

The front-door adapter force-sets both embedded loop flags to zero before Uvicorn starts.

### 4. Startup contention reduction

Dedicated engine and worker roles no longer repeat the large idempotent startup schema patch sweep by default. The engine retains the market-data startup self-check; the worker and front door skip it unless explicitly enabled. Controlled migration and pre-deploy diagnostics remain assigned to the front-door Railway service.

### 5. Role-specific database capacity

The split script sets independent `DB_ROLE`, `DB_APP_NAME`, session gates and Railway absolute pool caps:

- front door: `5+1`;
- engine: `4+1`;
- worker: `6+2`.

The total reviewed pooled maximum is 19 connections across one replica of each service, before transient auxiliary connections. The v1.3.5 runtime evidence reported PostgreSQL `max_connections=100`, but the post-split total must still be confirmed in Railway.

Database logging now distinguishes reviewed decomposed pools from unsafe monolith pools.

### 6. Neutral repository Railway configuration

`railway.json` now contains only the shared build/start/restart contract. HTTP healthcheck and pre-deploy commands are configured specifically on the front-door service by `split_signalrank_railway.ps1`, preventing engine and worker services from inheriting HTTP-only configuration.

### 7. Deployment tooling and regression protection

The release includes:

- `split_signalrank_railway.ps1`;
- `SIGNALRANK_RAILWAY_SPLIT_README.txt`;
- `SignalRankAI_v1.3.6_Railway_Performance_Decomposition.env.example`;
- `scripts/verify_v136_railway_performance_decomposition.py`;
- `tests/test_v136_railway_performance_decomposition.py`;
- regenerated governance registries.

## Safety boundary

This release does not enable unrestricted live broker execution, automatic copy trading, public automatic payouts or unreviewed financial activation. Staging safety remains fail-closed.
