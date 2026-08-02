# SignalRankAI v1.3.6.5 Deployment Guide

## 1. Apply the overlay locally

From the existing SignalRankAI project directory in Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$HOME\Downloads\SignalRankAI_v1.3.6.5_HOTFIX_OVERLAY\apply_signalrank_v1.3.6.5_hotfix.ps1" `
  -ProjectRoot (Get-Location).Path
```

The script creates a timestamped backup, copies the changed files and compiles the affected Python source.

## 2. Verify before committing

```powershell
python scripts/verify_v1365_production_integrity.py
python scripts/verify_v136_railway_performance_decomposition.py
python scripts/verify_v130_production_cutover.py
python -m compileall -q .
alembic heads
```

Expected migration head:

```text
0034_production_integrity (head)
```

Run the focused tests:

```powershell
python -m pytest -q `
  tests/test_v1365_production_integrity.py `
  tests/test_v1365_production_integrity_profile_routing.py `
  tests/test_signal_deduplicator.py `
  tests/test_signal_dedup_rules.py `
  tests/test_asset_repeat_policy.py `
  tests/test_paper_ledger_exits.py `
  tests/test_outcome_delivery_contract.py `
  tests/test_provider_and_asset_registry_hardening.py
```

## 3. Review and commit intentionally

```powershell
git status --short
git diff --stat
git diff --check

git add `
  RELEASE_FINGERPRINT.txt `
  core data db engine ml services signalrank_telegram worker railway_main.py `
  scripts tests `
  SignalRankAI_v1.3.6.5_*.md `
  SignalRankAI_v1.3.6.5_Railway.env.example

git commit -m "fix(production): harden signal integrity, paper trading and asset discovery"
git push
```

Do not stage `.env`, downloaded logs, database URLs, API keys, Telegram tokens or backup directories.

Record the exact 40-character commit:

```powershell
$releaseCommit = git rev-parse HEAD
$releaseCommit
```

## 4. Configure staging variables

Use `SignalRankAI_v1.3.6.5_Railway.env.example` as the safe baseline. Keep all real-money switches off:

```text
PRODUCTION_INTEGRITY_CERTIFIED=0
AUTO_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
GLOBAL_EXECUTION_KILL_SWITCH=1
```

Set the exact release commit on all three services:

```powershell
$services = @("SignalRankAI", "SignalRankAI-engine", "SignalRankAI-worker")
foreach ($service in $services) {
  railway variables `
    --service $service `
    --environment staging `
    --set "APP_VERSION=1.3.6.5" `
    --set "EXPECTED_RELEASE_COMMIT=$releaseCommit" `
    --set "APP_ENV=staging"
}
```

Use your actual current Railway service names when they have not yet been renamed.

## 5. Deploy the same commit to all roles

Deploy source/predeploy first so migration `0034` is applied once. Then deploy engine and worker from the same exact commit.

Recommended role ownership:

| Service | Role |
|---|---|
| `SignalRankAI` | front door, Telegram, HTTP |
| `SignalRankAI-engine` | discovery, analysis, scoring, generation |
| `SignalRankAI-worker` | outcomes, shadow, candles, paper, ML, pulse |

All services must use the same database and compatible state/delivery Redis references, while keeping role-specific pools and runtime flags.

## 6. Staging certification

### Readiness

```powershell
curl.exe -s https://YOUR-STAGING-DOMAIN.up.railway.app/readyz
```

Confirm:

- release commit matches;
- migration is `0034_production_integrity`;
- database and both Redis roles are healthy;
- provider coverage is present for every enabled asset class;
- Telegram is ready;
- outcome projection coverage is reported;
- live financial activation remains false.

### Signal deduplication

Generate or observe multiple nearby same-asset candidates. Confirm:

- only one independent thesis is stored in the four-hour window;
- a 15m/1h repricing cannot bypass the canonical fingerprint;
- the same user does not receive the same asset for four hours;
- different users remain independently eligible;
- owner/admin accounts do not bypass cooldown by default;
- failed delivery does not create a false confirmed cooldown.

### Dynamic asset discovery

Inspect `/assets`, engine logs and the asset registry. Confirm each admitted instrument has:

- online provider provenance;
- normalized symbol and asset class;
- supported timeframe/history;
- recent market data;
- liquidity/capability evidence;
- no static-only provenance while static fallback is disabled.

### Profile routing

Use two test profiles with different asset classes/timeframes. Confirm the common discovered universe is personalized correctly and that the same rules affect Telegram, paper, copy and live eligibility.

### Paper trading

Confirm:

- stale queued signals are rejected at actual fill time;
- a second position for the same asset is rejected;
- asset-class and total-exposure limits work;
- entry-deviation limits work;
- `/paper_close_all CONFIRM` closes all positions with evidence;
- reset succeeds only after closure;
- fresh signals can open after capacity is freed.

### Outcomes

Confirm TP/SL lifecycle order and projection:

- TP1 → TP2 → TP3 is monotonic;
- no delayed lower-stage event is sent after TP3;
- every proof-backed delivery has an outcome projection row;
- repeated notification workers cannot duplicate delivery;
- provider timestamps are fresh and recorded.

### Performance and calibration

Confirm:

- duplicate theses are counted once in public statistics;
- terminal coverage is displayed;
- a 60% claim remains `NOT ELIGIBLE` without the full evidence gate;
- uncalibrated cards say `Model Score (uncalibrated)`;
- only an evidence-qualified model says `Calibrated win probability`.

## 7. Earn certification IDs

Do not manually invent these IDs. Generate signed or durable reports from successful staging/canary runs and then set their report identifiers:

```text
PRODUCTION_INTEGRITY_CERTIFICATION_ID
LIVE_RUNTIME_CERTIFICATION_ID
ML_CALIBRATION_ARTIFACT_ID
COPY_TRADING_CERTIFICATION_ID
ASSET_DISCOVERY_CERTIFICATION_ID
FRESHNESS_CERTIFICATION_ID
PROFILE_ROUTING_CERTIFICATION_ID
PAPER_TRADING_CERTIFICATION_ID
OUTCOME_TRACKER_CERTIFICATION_ID
PERFORMANCE_TRUTH_CERTIFICATION_ID
```

For public win-rate claims, additionally require the statistical report/certification expected by the release guard.

## 8. Production canary

Production activation must start owner-only, one dedicated broker account, a small symbol allowlist and minimal exposure. Keep copy trading disabled during the first canary.

Required sequence:

1. deploy with all execution switches off;
2. verify readiness and exact commit;
3. run provider, freshness, profile and outcome canaries;
4. enable demo execution and broker reconciliation;
5. earn live runtime certification;
6. enable owner-only real execution for a short UTC activation window;
7. monitor fills, slippage, reconciliation and kill-switch behavior;
8. only then certify copy trading separately;
9. paid public launch comes after performance truth and operational SLOs remain stable.

Never disable the global kill switch or enable real execution simply to make readiness green.
