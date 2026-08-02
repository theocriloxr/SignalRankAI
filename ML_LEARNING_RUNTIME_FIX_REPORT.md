# SignalRankAI v1.3.5 ML Learning and Runtime Reliability Fix

## Basis

This package extends the referral-fixed codebase that was deployed from base commit
`07585aeb8ce8`. The package itself is not a Git commit; create a new commit after
reviewing and merging it.

Current migration head: `0033_ml_learning_runtime`.

## What the latest deployment log proved

- The reviewed Railway pool override is active at 12 pooled connections plus 4 overflow.
- PostgreSQL reported 100 maximum connections, 8 current connections, and 92 available.
- The outcome tracker, shadow tracker, paper worker, adaptive strategy layer, and threshold optimizer start.
- Threshold optimization changes score/confluence/ML operating thresholds.
- Predictive retraining is triggered, but the deployed version defers its training-data read whenever a foreground database lane is occupied.
- Adaptive candle persistence is deferred for the same reason.
- A second service/process continues to own the resend advisory lock.
- Outcome notification jobs overlap and are skipped because a previous 30-second run is still active.
- One Telegram/background database session remained open for 16.467 seconds.

## Runtime/database changes

### Reserve-aware database admission

`db/priority.py` and `db/session.py` now separate physical pool capacity from logical work classes:

- Foreground capacity is reserved for Telegram commands, delivery proofs, signal storage, and outcome transitions.
- Durable background work may use only the non-reserved pool portion.
- Background work no longer becomes completely disabled merely because one foreground command exists.
- Interactive and critical concurrency are configurable rather than permanently serialized to one session each.
- Callers can explicitly choose durable background waiting with `drop_if_busy=False`.

This preserves working command and delivery behavior while allowing ML, shadow tracking, and candle capture to progress.

## ML learning changes

### Multisource dataset

`ml/train_model.py` now assembles weighted evidence from:

| Evidence source | Default weight | Purpose |
|---|---:|---|
| Confirmed delivered live outcomes | 1.00 | Highest-confidence production labels |
| Delivery-proof-backed archived outcomes | 0.80 | Durable historical live evidence |
| Tracked rejected/shadow signals | 0.60 | False-negative and correct-block learning |
| Closed paper executions | 0.35 | Execution-aware supplemental evidence |
| Legacy unverified archive rows | 0.25 | Low-confidence historical supplement |

Candle history is loaded once per asset/timeframe series and sliced in memory for each signal instead of issuing a separate candle query per training row.

### Candidate versus active promotion

When total evidence is sufficient but live proof is below `ML_MIN_LIVE_PROOF_ROWS`:

- A candidate model is still trained from archive, shadow, paper, and available candle evidence.
- It is loaded into the shadow inference path.
- It cannot replace the active production model.
- It is stored durably as the `candidate` artifact.

When live-proof and quality gates pass:

- The model is atomically written.
- The running inference cache is reloaded immediately.
- The model is stored durably as the active `primary` artifact.
- Failure at reload or durable persistence restores the previous active model.

### Nonblocking model fitting

Feature engineering and XGBoost fitting now run outside the Telegram/event-loop thread via `asyncio.to_thread`. The outcome tracker schedules retraining as a separate task rather than awaiting the complete training operation inside an outcome scan.

### Accurate observability

A deferred dataset read is now reported as `read_status=deferred`, not as zero eligible outcomes. Successful runs emit source counts, effective sample count, live-proof count, validation metrics, artifact status, and active/candidate version.

## Candle and shadow reliability

- Adaptive candle bulk upserts wait for non-reserved background capacity instead of immediately dropping.
- Failed candle writes retain their pending batch for a later retry.
- Shadow outcome reads/writes use the durable background lane and configurable timeouts.
- Full candle sequences remain deduplicated by asset, timeframe, and candle open time.

## Durable Railway model storage

Migration `0033_ml_learning_runtime` adds `ml_model_artifacts` with:

- primary and candidate model names;
- artifact SHA-256 integrity;
- feature schema version;
- training metrics and evidence-source counts;
- one active artifact per model name.

`db/auto_ops.py` restores primary and candidate artifacts after an ephemeral Railway restart and reloads the inference caches.

## Files changed or added

- `db/priority.py`
- `db/session.py`
- `db/models.py`
- `db/auto_ops.py`
- `db/migrations/versions/0033_ml_learning_runtime.py`
- `ml/train_model.py`
- `ml/artifact_store.py`
- `engine/ml.py`
- `engine/realtime_outcome_tracker.py`
- `engine/adaptive/candle_store.py`
- `engine/shadow_outcome_worker.py`
- `tests/test_ml_learning_runtime_v135.py`
- migration-head verification tests/scripts
- `SignalRankAI_v1.3.5_ML_Learning_Runtime.env.example`

## Deployment

1. Stop any old Railway, Render, local, staging, or production process sharing the same database/Redis lock scope and Telegram token.
2. Merge this package into the repository.
3. Apply the supplied environment template in staging.
4. Run:

```bash
python -m alembic upgrade head
python -m alembic current
```

Expected head:

```text
0033_ml_learning_runtime (head)
```

5. Deploy one replica initially.
6. Trigger or wait for outcome tracking and ML retraining.

## Required proof after deployment

A healthy dataset/training cycle should show one of these two safe outcomes.

Candidate-only learning:

```text
[ml_dataset] status=success rows=<positive> live_proof=<below threshold> sources={...}
[ml_training_run] ... status=candidate_only
[ml_training_run] ... status=fitting
[ml_shadow_model_reload] {'loaded': True, ...}
[ml_artifact] persisted active model name=candidate
[ml_training_run] ... status=candidate_saved
```

Active promotion:

```text
[ml_dataset] status=success rows=<positive> live_proof=<at least threshold> sources={...}
[ml_training_run] ... status=fitting
[ml_model_saved]
[ml_model_reload] {'loaded': True, ...}
[ml_artifact] persisted active model name=primary
[ml_training_run] ... status=promoted
```

Candle/shadow proof:

```text
[adaptive_candles] persisted ...
[shadow_tracker] ... tracked=<positive or valid zero>
```

The following should disappear during normal capacity:

```text
ML training data read deferred ... foreground lane reserved
adaptive_candles persistence deferred ... foreground lane reserved
another instance holds advisory lock
```

## No-code response-speed actions

These can be done in Railway without changing source code:

1. Stop the duplicate process holding the advisory lock.
2. Set `DEPLOYMENT_DIAGNOSTICS_ENABLED=0` after a successful certification; the diagnostics subprocess starts while the engine is fetching market data and creates avoidable startup load.
3. Keep `BOT_COMMAND_SCOPE_BULK_REFRESH_ENABLED=0` and `ACTIVE_SIGNAL_KEYBOARD_REFRESH_ENABLED=0`.
4. Increase `OUTCOME_NOTIFICATION_INTERVAL_SECONDS` from 30 to 60 and `MONITOR_REFRESH_INTERVAL_SECONDS` from 60 to 120 to stop overlapping scheduler work.
5. Before deploying this patch, temporarily use `WEBHOOK_UPDATE_WORKERS=2` to reduce contention against the old one-slot interactive lane. After this patch, use 4.
6. Set `XGB_NTHREAD=1` on a 1-vCPU Railway service or 2 on a 2+-vCPU service.
7. Keep the application, PostgreSQL/PgBouncer, and both Redis services in the same Railway region and use their private URLs.
8. Increase Railway CPU/RAM before increasing worker counts. More webhook workers on a CPU-starved monolith will increase tail latency.

## Validation completed

- Python compilation passed for every modified runtime module.
- Alembic reports `0033_ml_learning_runtime` as the single head.
- 80 targeted tests passed across ML registry/schema, database admission, candle persistence, referral reliability, outcome tracking, paper reliability, and production-price handling.
- Four additional Telegram-level tests could not be collected in this analysis container because `python-telegram-bot` and `APScheduler` are not installed here. The package requirements already declare them, and the failure was dependency collection rather than a failed assertion.

A live Railway training promotion cannot be proven until this build is deployed against the real database and produces the required proof logs.
