SignalRankAI v1.3.6 Railway performance decomposition
=====================================================

Purpose
-------
Move the current RUN_MODE=all Railway monolith into three single-owner services
so Telegram command latency, signal scanning, outcomes, candle persistence and ML
learning no longer compete in the same process/event loop/database admission lane.

Topology
--------
1. SignalRankAI (front door)
   - RUN_MODE=frontdoor
   - FastAPI /readyz, /healthz, /metrics/prometheus and Telegram webhook
   - Telegram commands/callbacks, bot scheduler, delivery/retry jobs
   - Embedded signal engine: HARD DISABLED
   - Embedded background worker: HARD DISABLED

2. SignalRankAI-engine
   - RUN_MODE=engine
   - Signal universe, market-data fetch, analysis, scoring and signal generation
   - No Telegram webhook, no bot scheduler, no legacy worker loop

3. SignalRankAI-worker
   - RUN_MODE=worker (boot metadata may show delivery because worker is a legacy alias)
   - Outcome tracking, shadow outcomes, candle capture, paper trading, ML retraining,
     retry workers and daily Engine Pulse
   - No Telegram webhook and no signal-generation engine

Why this release is different
-----------------------------
The split is enforced by source code, not only Railway variables:
- frontdoor is a first-class runtime role;
- stale RUN_ENGINE_LOOP=1 or RUN_WORKER_LOOP=1 cannot re-enable loops there;
- decomposed topology refuses RUN_MODE=all and unknown-role monolith fallback;
- each service gets an explicit DB_ROLE and reviewed absolute pool cap;
- engine/worker skip duplicate startup schema patch sweeps;
- railway.json is neutral so non-HTTP roles do not inherit /readyz or pre-deploy work.

Run from PowerShell in the repository root
------------------------------------------
Set-ExecutionPolicy -Scope Process Bypass
.\split_signalrank_railway.ps1 -Environment staging -SourceService SignalRankAI

Optional region pinning
-----------------------
.\split_signalrank_railway.ps1 `
  -Environment staging `
  -SourceService SignalRankAI `
  -Region eu-west

The script:
- creates SignalRankAI-engine and SignalRankAI-worker when absent;
- copies shared secrets/config while excluding role and pool ownership variables;
- configures explicit frontdoor/engine/worker ownership;
- assigns migrations and HTTP readiness only to the front door;
- deploys front door first so embedded loops stop before dedicated services start;
- deploys engine and worker with one role each.

Required proof after deployment
-------------------------------
Front door logs must contain:
  [runtime_ownership] mode=frontdoor ... engine=false worker=false
  Engine loop skipped by ownership mode=frontdoor
  Worker loop skipped by ownership mode=frontdoor
  webhook mode active

Front door logs must NOT contain:
  Engine loop task created
  Worker loop task created

Engine logs must contain:
  [boot] starting | run_mode=engine
  [engine] background/main loop activity and provider fetches

Worker logs must contain:
  [boot] starting | run_mode=delivery
  RealtimeOutcomeTracker started
  ShadowOutcomeTracker started
  AdaptiveCandleCapture started
  PaperTradingWorker started

All services must show their own database application role:
  signalrankai/frontdoor
  signalrankai/engine
  signalrankai/worker

Operational checks
------------------
railway logs --service SignalRankAI --environment staging --latest --lines 300
railway logs --service SignalRankAI-engine --environment staging --latest --lines 300
railway logs --service SignalRankAI-worker --environment staging --latest --lines 300

curl https://<frontdoor-domain>/healthz
curl https://<frontdoor-domain>/readyz
curl https://<frontdoor-domain>/metrics/prometheus

Keep every service at one replica for certification. Do not scale the front door
above one until command execution, bot scheduling and delivery are decomposed into
separate leased services.
