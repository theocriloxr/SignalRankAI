# SignalRankAI v1.3.6.7 Deployment and Runtime Verification

## 1. Apply the overlay

From the existing SignalRankAI project directory:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$HOME\Downloads\SignalRankAI_v1.3.6.7_HOTFIX_OVERLAY\apply_signalrank_v1.3.6.7_hotfix.ps1" `
  -ProjectRoot (Get-Location).Path
```

## 2. Validate locally

```powershell
& ".\.audit-venv\Scripts\Activate.ps1"
python -m pip install -r requirements.txt
python scripts/verify_v1367_integrity_accounting_hotfix.py
python scripts/verify_v1366_runtime_certification_hotfix.py
python scripts/verify_v1365_production_integrity.py
python scripts/schema_audit.py --json
python scripts/build_v7_governance.py --check
python -m compileall -q .
python -m pytest -q
```

Expected Alembic head remains:

```text
0034_production_integrity
```

No database migration is added by this release.

## 3. Inspect legacy duplicates before deployment

Run dry-run only first against staging:

```powershell
python scripts/repair_active_signal_duplicates.py `
  --days 30 `
  --hours 4 `
  --entry-tolerance 0.003 `
  --output duplicate-repair-preview.json
```

Review every proposed canonical/duplicate pair. The report deletes no rows.

Apply only after review:

```powershell
python scripts/repair_active_signal_duplicates.py `
  --apply `
  --days 30 `
  --hours 4 `
  --entry-tolerance 0.003 `
  --output duplicate-repair-applied.json
```

The apply mode preserves signal, delivery and audit history. It retires later near-identical active rows, closes unresolved duplicate tracking state as excluded/cancelled, and records an admin audit event.

## 4. Commit one immutable release

```powershell
git status --short
git diff --check
git add -A
git commit -m "fix(integrity): repair partial exits and enforce semantic dedup"
git push
$releaseCommit = git rev-parse HEAD
$releaseCommit
```

## 5. Configure every Railway service

```powershell
$services = @(
  "bountiful-miracle",
  "striking-optimism",
  "SignalRankAI"
)

foreach ($service in $services) {
  railway variables `
    --service $service `
    --environment staging `
    --set "APP_VERSION=1.3.6.7" `
    --set "EXPECTED_RELEASE_COMMIT=$releaseCommit" `
    --set "SIGNAL_THESIS_DEDUP_HOURS=4" `
    --set "SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT=0.003" `
    --set "THESIS_FINGERPRINT_INCLUDE_REGIME=0" `
    --set "THESIS_FINGERPRINT_INCLUDE_TIMEFRAME=0" `
    --set "ASSET_REPEAT_LOCK_HOURS=4" `
    --set "ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES=0" `
    --set "ALLOW_ASSET_COOLDOWN_REDUCTION=0"
}
```

Worker variables:

```powershell
railway variables `
  --service SignalRankAI `
  --environment staging `
  --set "OUTCOME_RECONCILIATION_ENABLED=1" `
  --set "OUTCOME_RECONCILIATION_INTERVAL_SECONDS=60" `
  --set "OUTCOME_RECONCILIATION_STARTUP_DELAY_SECONDS=5" `
  --set "OUTCOME_RECONCILIATION_LIMIT=5000" `
  --set "PARTIAL_EXIT_REPAIR_DAYS=365" `
  --set "PARTIAL_EXIT_REPAIR_LIMIT=2000" `
  --set "SIGNAL_TP1_CLOSE_FRACTION=0.50" `
  --set "SIGNAL_TP2_CLOSE_FRACTION=0.25" `
  --set "PAPER_CLOSE_ALL_LAST_MARK_MAX_AGE_SECONDS=300"
```

Front-door variables:

```powershell
railway variables `
  --service bountiful-miracle `
  --environment staging `
  --set "OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED=1" `
  --set "OUTCOME_NOTIFICATION_JOB_BUDGET_SECONDS=45" `
  --set "OUTCOME_NOTIFICATION_HISTORICAL_AFTER_SECONDS=300" `
  --set "OUTCOME_NOTIFICATION_FETCH_MARKET_PRICE_FALLBACK=0" `
  --set "OUTCOME_NOTIFICATION_PRICE_TIMEOUT_SECONDS=3"
```

Keep live, copy, payments-public and performance-marketing switches off.

## 6. Required worker proof

```powershell
railway logs `
  --service SignalRankAI `
  --environment staging `
  --lines 4000 |
  Select-String `
    "outcome_reconciliation|partial_exit_repairs|performance=|partial_exit_accounting|paper_worker_cycle|Traceback|ERROR"
```

Pass criteria:

- reconciliation completes with `failed=0`;
- `partial_exit_repairs` becomes positive when legacy rows exist, then returns to zero on later idempotent cycles;
- performance rows change under `proof-ledger-v2-partial-exit`;
- no repeated partial-exit repair of already-current rows;
- paper cycles remain `failed=0`.

## 7. Required engine dedup proof

Use controlled staging signals that recreate the observed failures:

1. exact SOL duplicate: same asset/direction/strategy/entry/SL/TP, two minutes apart;
2. near-price BNB duplicate: same thesis with entries differing by less than 0.3%;
3. same thesis across 5m and 1h;
4. same asset but materially different entry beyond tolerance after the four-hour window.

```powershell
railway logs `
  --service striking-optimism `
  --environment staging `
  --lines 5000 |
  Select-String `
    "semantic thesis reused|thesis_fingerprint|stored=|signal-thesis:|dedup|Failed to persist signal|Traceback|ERROR"
```

Required result:

- cases 1–3 reuse one canonical signal ID;
- case 4 may create a new signal only when all admission rules pass;
- no duplicate Signal row is stored due to concurrent engine replicas.

## 8. Required delivery proof

Test with an owner/admin account and a normal account.

```powershell
railway logs `
  --service bountiful-miracle `
  --environment staging `
  --lines 5000 |
  Select-String `
    "asset_lock|DB deduped before send|Creating new delivery|suppressed duplicate thesis recipient|delivery_attempt_start|delivery_proof_write|Traceback|ERROR"
```

Pass criteria:

- owner/admin receives no second signal for the same asset within four hours;
- normal user behavior remains identical;
- failed or blocked sends do not create a false sent cooldown;
- a confirmed send creates durable delivery proof;
- a historical duplicate outcome is suppressed rather than sent as a separate terminal trade.

## 9. Verify `/performance`

Run after at least one known TP1→protected exit and one TP2→protected exit:

```text
/performance
/performance audit
```

Required result:

```text
Stopped TP1 / TP2: <non-zero values matching lifecycle evidence>
Duplicate thesis deliveries excluded: <count where legacy duplicates exist>
```

Cross-check worker logs and the ledger. TP1/TP2 protected exits must have positive or zero weighted R according to the configured scale-out plan, not `-1R`.

## 10. Recover paper trading safely

```text
/paper_positions
/paper_close_all CONFIRM
```

When a provider is temporarily unavailable and the stored marks are no older than the configured limit:

```text
/paper_close_all FORCE CONFIRM
```

Then:

```text
/paper_positions
/paper_reset 10000 CONFIRM
/paper_settings
```

Prove that one fresh eligible signal opens, a second same-asset signal is blocked, stale signals do not reopen, and exposure/daily-loss/open-risk gates remain active.

## 11. Verify terminal notifications

```powershell
railway logs `
  --service bountiful-miracle `
  --environment staging `
  --lines 5000 |
  Select-String `
    "\[outcome\]|job budget exhausted|deferring notify mark|notification already claimed|Signal ID|Historical reconciliation|Traceback|ERROR"
```

Required result:

- every terminal message includes its full Signal ID and evidence;
- TP1/TP2 protected exits are not labelled full SL losses;
- after successful delivery, the outcome leaves the unnotified queue;
- no same terminal event loops indefinitely with `sent=0`;
- quiet-hour recipients are deferred without losing their notification.

## 12. Readiness

```powershell
curl.exe -s https://bountiful-miracle-staging.up.railway.app/readyz |
  python -m json.tool
```

The next milestone requires matching release identity, outcome coverage at least 0.99, performance-ledger projection at least 0.99, healthy Telegram/Redis/database/shadow checks and no new runtime integrity error.
