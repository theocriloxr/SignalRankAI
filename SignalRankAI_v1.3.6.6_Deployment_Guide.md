# SignalRankAI v1.3.6.6 Deployment and Runtime Verification

## Apply locally

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$HOME\Downloads\SignalRankAI_v1.3.6.6_HOTFIX_OVERLAY\apply_signalrank_v1.3.6.6_hotfix.ps1" `
  -ProjectRoot (Get-Location).Path
```

Then:

```powershell
& ".\.audit-venv\Scripts\Activate.ps1"
python -m pip install -r requirements.txt
python scripts/verify_v1366_runtime_certification_hotfix.py
python scripts/verify_v1365_production_integrity.py
python scripts/schema_audit.py --json
python scripts/build_v7_governance.py --check
python -m compileall -q .
python -m pytest -q
```

Expected migration head remains `0034_production_integrity`.

## Commit and deploy

```powershell
git status --short
git diff --check
git add -A
git commit -m "fix(runtime): unblock reconciliation and reject weak ML promotion"
git push
$releaseCommit = git rev-parse HEAD
```

Deploy the same commit to front door, engine and worker. Set on all services:

```powershell
$services = @("bountiful-miracle", "striking-optimism", "SignalRankAI")
foreach ($service in $services) {
  railway variables `
    --service $service `
    --environment staging `
    --set "APP_VERSION=1.3.6.6" `
    --set "EXPECTED_RELEASE_COMMIT=$releaseCommit"
}
```

Set on the worker:

```powershell
railway variables `
  --service SignalRankAI `
  --environment staging `
  --set "OUTCOME_RECONCILIATION_ENABLED=1" `
  --set "OUTCOME_RECONCILIATION_INTERVAL_SECONDS=60" `
  --set "OUTCOME_RECONCILIATION_STARTUP_DELAY_SECONDS=5" `
  --set "OUTCOME_RECONCILIATION_LIMIT=5000" `
  --set "ML_MIN_PROMOTION_AUC=0.60" `
  --set "ML_MIN_PROMOTION_ACCURACY=0.55" `
  --set "ML_PROMOTION_REQUIRES_VALID_CALIBRATION=1"
```

Set on the front door:

```powershell
railway variables `
  --service bountiful-miracle `
  --environment staging `
  --set "OUTCOME_NOTIFICATION_FETCH_MARKET_PRICE_FALLBACK=0" `
  --set "OUTCOME_NOTIFICATION_PRICE_TIMEOUT_SECONDS=3"
```

Keep all live, copy and marketing switches off.

## Required log proof

Worker:

```powershell
railway logs `
  --service SignalRankAI `
  --environment staging `
  --lines 2000 |
  Select-String "outcome_reconciliation|performance=|InvalidColumnReferenceError|ml_training_run|candidate_only|status=rejected|status=promoted|Traceback|ERROR"
```

Pass criteria:

- no `InvalidColumnReferenceError`;
- reconciliation logs `completed` with `failed=0`;
- outcome coverage progresses to at least `0.99`;
- performance-ledger rows are created;
- the previously observed 0.50/0.575 model would be `status=rejected`, never promoted;
- an uncalibrated otherwise-good model is `candidate_only`.

Front door:

```powershell
railway logs `
  --service bountiful-miracle `
  --environment staging `
  --lines 1500 |
  Select-String "\[outcome\]|job budget exhausted|resend|advisory lock|max.*instances|Traceback|ERROR"
```

Pass criteria:

- terminal notifications reach recipients;
- the same outcome is not indefinitely deferred with `sent=0`;
- no scheduler overlap or advisory-lock loop;
- stale resend candidates continue to be rejected.

Readiness:

```powershell
curl.exe -s https://bountiful-miracle-staging.up.railway.app/readyz | python -m json.tool
```

The next milestone is:

- `release_identity.confirmed=true`;
- `outcome_projection.ok=true` and coverage at least `0.99`;
- performance-ledger projection approaching/meeting the configured threshold;
- Telegram, database, Redis, shadow tracker and schema checks healthy.

After historical reconciliation finishes, restore the worker interval to 300 seconds.
