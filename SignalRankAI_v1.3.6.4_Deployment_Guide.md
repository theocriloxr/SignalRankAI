# Deploy SignalRankAI v1.3.6.4

## Apply the overlay on Windows

Place the extracted hotfix overlay package anywhere, open PowerShell in the SignalRankAI project, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass

& "C:\path\to\SignalRankAI_v1.3.6.4_HOTFIX_OVERLAY\apply_signalrank_v1.3.6.4_hotfix.ps1" `
  -ProjectRoot (Get-Location).Path
```

The script backs up every replaced file and compiles the changed Python modules.

## Inspect and test

```powershell
git status --short
git diff --stat

python -m pytest -q `
  tests/test_phase12_performance_paper_reliability.py `
  tests/test_phase4_pass1_live_validation.py `
  tests/test_phase4_pass1_quote_contract.py `
  tests/test_v132_auto_delivery_callbacks_monitor.py `
  tests/test_v136_railway_performance_decomposition.py `
  tests/test_v1364_runtime_stability_hotfix.py
```

Expected focused result: `78 passed` or more if additional tests are present locally.

## Commit

```powershell
git add `
  core/env.py `
  core/job_leases.py `
  data/get_live_price.py `
  railway_main.py `
  services/delivery_authorization.py `
  services/performance_ledger.py `
  signalrank_telegram/bot.py `
  tests/test_phase12_performance_paper_reliability.py `
  tests/test_phase4_pass1_live_validation.py `
  tests/test_v132_auto_delivery_callbacks_monitor.py `
  tests/test_v1364_runtime_stability_hotfix.py `
  SignalRankAI_v1.3.6.4_Railway.env.example `
  SignalRankAI_v1.3.6.4_Runtime_Stability_Hotfix_Release_Notes.md `
  SignalRankAI_v1.3.6.4_Certification_Report.md `
  SignalRankAI_v1.3.6.4_Deployment_Guide.md

git commit -m "fix(runtime): stabilize scheduler ownership, ledger reconciliation, and providers"
git push
```

Do not stage `.env`, Railway secret exports, database URLs, or backup directories.

## Update front-door Railway variables

For the current staging front door:

```powershell
railway variables `
  --service bountiful-miracle `
  --environment staging `
  --set "APP_VERSION=1.3.6" `
  --set "RESEND_UNSENT_INTERVAL_SECONDS=60" `
  --set "RESEND_JOB_TIMEOUT_SECONDS=25" `
  --set "RESEND_JOB_BUDGET_SECONDS=20" `
  --set "RESEND_JOB_LEASE_SECONDS=45" `
  --set "RESEND_MAX_USERS_PER_RUN=6" `
  --set "RESEND_MAX_SIGNALS=3" `
  --set "RESEND_SKIP_WHEN_CRITICAL_DB_ACTIVE=1" `
  --set "OUTCOME_NOTIFICATION_INTERVAL_SECONDS=90" `
  --set "OUTCOME_NOTIFICATION_JOB_BUDGET_SECONDS=20" `
  --set "OUTCOME_NOTIFICATION_JOB_LEASE_SECONDS=45" `
  --set "OUTCOME_NOTIFICATION_MAX_OUTCOMES_PER_RUN=5" `
  --set "MONITOR_REFRESH_INTERVAL_SECONDS=120" `
  --set "DB_BACKGROUND_JOBS_SKIP_WHEN_CRITICAL_ACTIVE=1"
```

Configure one trusted FX/metals provider in Railway. For MetaApi, set the existing secret `META_API_TOKEN` and an explicit `META_API_MARKET_DATA_ACCOUNT_ID`. Never paste secrets into terminal output that will be shared.

## Verify all deployments

```powershell
railway service status --all --environment staging

railway logs `
  --service bountiful-miracle `
  --environment staging `
  --lines 500
```

Use the actual current service names until the services are renamed:

- `bountiful-miracle`: front door
- `striking-optimism`: engine
- `SignalRankAI`: worker

## Runtime certification

```powershell
curl.exe -s https://bountiful-miracle-staging.up.railway.app/readyz
```

Then:

1. Run `/performance` twice quickly.
2. Send `/start` and another command.
3. Click multiple inline buttons.
4. Wait through at least three resend intervals and three outcome intervals.
5. Inspect logs for:
   - `UniqueViolationError`
   - `uq_performance_ledger_scope`
   - `maximum number of running instances reached`
   - `another instance holds advisory lock`
   - `:production` in staging lock/ledger scope
   - `All providers failed for XAGUSD`

Normal healthy ownership logs may say a replica is in `standby` because another owner holds a Redis lease. That is expected and is different from the old stale advisory-lock defect.
