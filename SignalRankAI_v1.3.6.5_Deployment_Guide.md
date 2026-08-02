# SignalRankAI v1.3.6.5 Deployment and Certification Guide

This guide deploys the release safely. It does not bypass the live-money or public-claim gates.

## 1. Apply the overlay locally

Extract `SignalRankAI_v1.3.6.5_HOTFIX_OVERLAY.zip` outside the repository. From the existing SignalRankAI project directory in Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$HOME\Downloads\SignalRankAI_v1.3.6.5_HOTFIX_OVERLAY\apply_signalrank_v1.3.6.5_hotfix.ps1" `
  -ProjectRoot (Get-Location).Path
```

The script creates a timestamped backup, copies the overlay, compiles the affected source and runs the v1.3.6.5 integrity verifier.

## 2. Install the declared dependencies

Activate the project virtual environment, then install the repository requirements:

```powershell
& ".\.audit-venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Confirm the two runtime packages that were unavailable in the packaging container:

```powershell
python -c "import telegram, apscheduler; print('runtime imports OK')"
```

## 3. Validate locally

```powershell
python scripts/verify_v1365_production_integrity.py
python scripts/schema_audit.py --json
python scripts/build_v7_governance.py --check
python -m compileall -q .
alembic heads
```

Expected migration head:

```text
0034_production_integrity (head)
```

Run the production-focused regression matrix:

```powershell
python -m pytest -q `
  tests/test_v1365_production_integrity.py `
  tests/test_v1365_production_integrity_profile_routing.py `
  tests/test_v1364_runtime_stability_hotfix.py `
  tests/test_signal_deduplicator.py `
  tests/test_paper_ledger_exits.py `
  tests/test_signal_monitoring_reliability.py `
  tests/test_outcome_delivery_contract.py `
  tests/test_provider_and_asset_registry_hardening.py `
  tests/test_v131_live_financial_activation.py `
  tests/test_v136_railway_performance_decomposition.py `
  tests/test_staged_release_contracts.py `
  tests/test_runtime_hardening_contract.py `
  tests/test_broker_execution_p0.py `
  tests/test_canonical_broker_entrypoints.py
```

Then run the full local suite now that Telegram and APScheduler are installed:

```powershell
python -m pytest -q
```

Do not deploy when the full local suite has genuine failures.

## 4. Review and commit

```powershell
git status --short
git diff --stat
git diff --check
```

Do not stage `.env`, logs, backup folders, database URLs, API keys, Telegram tokens, broker credentials or exported Railway variables.

```powershell
git add -A
git commit -m "fix(production): harden integrity, profiles, outcomes and discovery"
git push

$releaseCommit = git rev-parse HEAD
$releaseCommit
```

Record the exact 40-character commit. Every Railway role must deploy that same commit.

## 5. Railway role mapping

Your current names may still be:

| Current service | Actual role |
|---|---|
| `bountiful-miracle` | front door / Telegram / HTTP |
| `striking-optimism` | engine / discovery / signal generation |
| `SignalRankAI` | worker / outcomes / paper / ML / pulse |

Recommended names after stability is confirmed:

| Recommended service | Role |
|---|---|
| `SignalRankAI` | front door |
| `SignalRankAI-engine` | engine |
| `SignalRankAI-worker` | worker |

Only the front door receives a public domain.

## 6. Configure safe staging variables

Use `SignalRankAI_v1.3.6.5_Railway.env.example` as the baseline. Keep all real-money and marketing switches off.

For the current service names:

```powershell
$services = @("bountiful-miracle", "striking-optimism", "SignalRankAI")
foreach ($service in $services) {
  railway variables `
    --service $service `
    --environment staging `
    --set "APP_VERSION=1.3.6.5" `
    --set "APP_ENV=staging" `
    --set "EXPECTED_RELEASE_COMMIT=$releaseCommit" `
    --set "PRODUCTION_INTEGRITY_CERTIFIED=0" `
    --set "LIVE_FINANCIAL_FEATURES_ENABLED=0" `
    --set "AUTO_EXECUTION_ENABLED=0" `
    --set "AUTO_TRADE_ENABLED=0" `
    --set "COPY_TRADE_ENABLED=0" `
    --set "REAL_EXECUTION_ENABLED=0" `
    --set "GLOBAL_EXECUTION_KILL_SWITCH=1" `
    --set "PUBLIC_WIN_RATE_MARKETING_ENABLED=0" `
    --set "ALLOW_STATIC_ASSET_FALLBACK=0"
}
```

Do not populate certification IDs yet.

### Front-door variables

The front door keeps Telegram/HTTP ownership. It must not run engine or worker ownership.

```text
RUN_MODE=frontdoor
DECOMPOSED_TOPOLOGY_ENABLED=1
```

Keep the working public URL in all relevant base/webhook variables.

### Engine variables

```text
RUN_MODE=engine
PROFILE_DRIVEN_UNIVERSE_ENABLED=1
PROFILE_DRIVEN_TIMEFRAMES_ENABLED=1
AUTO_DISCOVERY_ALL_PROVIDERS=1
ALLOW_STATIC_ASSET_FALLBACK=0
```

Configure only providers you actually use. Discovery must show provider provenance and sufficient history/liquidity before certification.

### Worker variables

```text
RUN_MODE=delivery
OUTCOME_RECONCILIATION_ENABLED=1
OUTCOME_RECONCILIATION_INTERVAL_SECONDS=300
SHADOW_OUTCOME_TRACKER_ENABLED=1
WORKER_SHADOW_TRACKER_ENABLED=1
WORKER_ENGINE_PULSE_ENABLED=1
PAPER_TRADING_ENABLED=1
```

The worker owns continuous outcome projection, performance-ledger reconciliation, shadow tracking, paper management, adaptive capture/ML and Engine Pulse.

## 7. Apply migration 0034

Deploy the release/predeploy-capable service first so migration `0034_production_integrity` runs once. Verify:

```powershell
railway logs `
  --service bountiful-miracle `
  --environment staging `
  --lines 400 |
  Select-String "0034_production_integrity|alembic|migration|ERROR|Traceback"
```

Do not continue when the database head is not `0034_production_integrity`.

## 8. Deploy all roles from the same commit

Deploy front door, engine and worker from the exact same pushed commit. Verify each service status:

```powershell
railway service status --all --environment staging
```

## 9. Verify readiness and ownership

```powershell
curl.exe -i https://bountiful-miracle-staging.up.railway.app/readyz
```

The response must be application-generated `200 OK`, not Railway fallback. Inspect these checks:

```text
database
state_redis
delivery_redis
provider_coverage
outcome_projection
performance_ledger
shadow_tracker
engine_pulse
telegram
telegram_webhook_secret
```

Search service logs:

```powershell
$services = @("bountiful-miracle", "striking-optimism", "SignalRankAI")
foreach ($service in $services) {
  Write-Host "`n===== $service ====="
  railway logs --service $service --environment staging --lines 700 |
    Select-String "runtime_ownership|run_mode=|0034_production_integrity|ERROR|Traceback|advisory lock|max.*instances|provider_coverage|outcome_reconciliation"
}
```

Expected ownership:

- front door: HTTP/Telegram, no engine/worker loops;
- engine: discovery/scanning/generation, no Telegram scheduler;
- worker: outcome/paper/shadow/ML/pulse, no public HTTP ownership.

## 10. Telegram functional certification

Run and record evidence for:

```text
/start
/system
/ops_health
/assets
/signals
/performance
/performance audit
/paper_settings
/paper_positions
/paper_performance
/release_guard
```

Also test:

- inline callback acknowledgement;
- profile update and delivery filtering;
- same-user same-asset four-hour cooldown;
- same thesis across 15m/1h and tiny repricing;
- fresh vs stale delivery;
- paper rejection for stale/duplicate/concentrated positions;
- `/paper_close_all CONFIRM` followed by reset;
- monotonic TP1 → TP2 → TP3 or SL notifications;
- no TP1/TP2 notification after terminal TP3/SL;
- command latency under normal and signal-delivery load.

## 11. Dynamic asset-discovery certification

Capture evidence that the engine:

1. fetched online/provider instrument catalogues;
2. filtered active/tradable instruments;
3. ranked liquidity/capability;
4. rejected unsupported or stale symbols;
5. persisted provider/discovery provenance;
6. shaped priority/timeframes from active user profiles;
7. did not silently use static fallback.

Use `/assets`, `/engine_debug`, provider logs and database provenance fields. Validate every enabled asset class separately.

## 12. Staging soak acceptance gates

Do not create certification IDs until the relevant evidence passes. At minimum verify:

- zero unintended same-user/same-asset repeats inside four hours;
- zero duplicate open paper positions per asset;
- zero stale paper/copy/live fills;
- no outcome-stage regression;
- proof-backed outcome projection coverage at or above the configured threshold;
- performance terminal coverage at or above the configured threshold;
- no unverified public performance output;
- shadow tracker heartbeat and real evaluated rejects when rejects exist;
- Engine Pulse counter invariants and delivery attribution;
- profile routing consistency across generation demand, delivery, paper and broker routing;
- provider coverage and discovery provenance;
- no secret leakage;
- no repeated tracebacks, lock contention loops or scheduler overruns.

## 13. Broker demo certification

Use broker demo/test accounts only. Validate order normalization, minimum sizes, slippage, reconciliation, partial fills, TP/SL placement, restart recovery, duplicate prevention, kill switch and account allowlists.

Generate a real demo certification report ID only after evidence is reviewed.

## 14. Owner-only limited live activation

Only after every required evidence ID exists, prepare a tightly limited production activation:

- one owner Telegram ID;
- exact broker account allowlist;
- exact provider allowlist;
- very small exact symbol allowlist;
- strict maximum position, daily loss and total exposure;
- activation window no longer than 24 hours;
- dedicated broker account;
- manual monitoring and tested kill switch.

Evaluate `/release_guard` and financial activation before clearing the kill switch. A blocked check means do not trade live.

## 15. Copy trading and paid beta

Copy trading requires its own certification after owner-only live execution is stable. Paid beta should remain owner-controlled and should not advertise uncertified performance.

Payments, subscriptions, receipts, refunds, entitlement enforcement and support workflows require their own end-to-end staging tests before paid launch.

## 16. Public performance claims

A `60%+` claim is never manually enabled merely because the observed rate crosses 60%. The independent-thesis sample, terminal coverage and 95% Wilson lower bound must all pass, and the performance claim must have a dedicated reviewed certification ID.

Until then, keep:

```text
PUBLIC_WIN_RATE_MARKETING_ENABLED=0
PERFORMANCE_CLAIM_CERTIFICATION_ID=
```

## 17. Rollback

The overlay application creates `.signalrank-backups\v1.3.6.5-<timestamp>`. For deployment rollback, restore the previous Git commit and redeploy all three roles from the same commit. Do not downgrade the database blindly after migration `0034`; use a reviewed database rollback plan or forward fix.
