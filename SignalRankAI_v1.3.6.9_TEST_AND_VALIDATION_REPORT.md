# SignalRankAI v1.3.6.9 Test and Validation Report

Date: 2026-08-03
Candidate: `v1.3.6.9-outcome-delivery-recovery-hotfix-20260803`
Verdict: suitable for controlled staging; not production-certified

## Log diagnosis

- Worker capture: 137 `persist_outcome error: name '_env_bool' is not defined` occurrences.
- Performance reconciliation: repeated batches examined six users with `failed_users=0`, confirming the v1.3.6.8 ledger fix improved the original blocker.
- Front door: the scheduled outcome notification job ran repeatedly, but no durable outcome/outbox rows were available because persistence rolled back.
- Front door: 23 resend budget-exhaustion messages and webhook p99 warnings at 6.247 seconds.
- Worker: XAGUSD live quotes repeatedly failed across configured providers, while a separate yfinance candle route sometimes returned OHLC.
- Worker: Paystack recovery remained disabled because the key pair was incomplete.
- Engine: TradingView rate-limit circuit opened repeatedly.

## Validation performed

### Static release verifier

```bash
python scripts/verify_v1369_outcome_delivery_recovery.py
```

Result: all checks passed.

### v1.3.6.8 foundation verifier

```bash
python scripts/verify_v1368_performance_scale_hotfix.py
```

Result: all retained-foundation checks passed.

### Hotfix and integrity regression group

```bash
pytest -q \
  tests/test_v1369_outcome_delivery_recovery.py \
  tests/test_v1368_performance_scale_hotfix.py \
  tests/test_phase12_performance_paper_reliability.py \
  tests/test_v1367_integrity_accounting_hotfix.py \
  tests/test_v1366_runtime_certification_hotfix.py \
  tests/test_v1365_production_integrity.py \
  tests/test_v1365_production_integrity_profile_routing.py \
  tests/test_v1364_runtime_stability_hotfix.py \
  tests/test_paper_ledger_exits.py \
  tests/test_timezone_and_performance_v2.py \
  tests/test_signal_dedup_rules.py \
  tests/test_signal_deduplicator.py \
  tests/test_v131_notification_delivery_integrity.py
```

Result: **131 passed**.

### Additional outcome/readiness group

Result: **69 passed, 3 deselected**. The deselected tests import `railway_main` and require the repository's declared `APScheduler`/`python-telegram-bot` runtime packages, which are unavailable and cannot be downloaded in this sandbox.

### Schema audit

```text
ok=true
heads=[0034_production_integrity]
revisions=34
outcome_projection_contract.ok=true
signal_runtime_contract.ok=true
live_financial_contract.ok=true
ml_rejected_runtime_contract.ok=true
```

### Compilation

`python -m compileall -q .` passed for the complete package.

## What local validation cannot prove

- Real PostgreSQL transaction/trigger behaviour under Railway load.
- Redis lease and cross-replica backoff behaviour.
- Telegram flood limits and exactly-once user delivery.
- Historical outbox replay count.
- Webhook p95/p99 after deployment.
- Provider/testnet/execution functionality not implemented in this release.
- 100,000-user throughput, failover, cost or disaster-recovery certification.

Use the staging checklist before any production decision.
