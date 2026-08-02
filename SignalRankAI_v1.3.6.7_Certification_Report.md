# SignalRankAI v1.3.6.7 Source Certification Report

Date: 2026-08-02
Fingerprint: `v1.3.6.7-integrity-accounting-dedup-hotfix-20260802`

## Source result

- Integrity-accounting verifier: **PASS**
- Inherited production-integrity verifier: **PASS**
- Python compilation: **PASS**
- Focused integrity/performance/dedup matrix: **108 passed; 3 additional imports blocked only by missing APScheduler in this container**
- Dependency-independent broad matrix after governance refresh: **446 passed, 1 skipped**
- Database migration head: unchanged at `0034_production_integrity`
- Runtime activation: **BLOCKED pending redeployment evidence**

## Deterministically verified

- TP1 protected exit under the default scale-out plan: `+0.60R` in the test fixture.
- TP2 protected exit under the default scale-out plan: `+1.05R` in the test fixture.
- `partial_win_be` maps to `STOPPED_AT_TP1` or `STOPPED_AT_TP2` according to lifecycle evidence.
- Historical partial-exit outcomes and ML labels are repairable and idempotent.
- Exact and semantic thesis admission are serialized across engine replicas.
- Regime/timeframe changes do not create a new fingerprint by default.
- Owner/admin delivery deduplication bypasses are absent.
- Four-hour same-asset policy cannot be weakened accidentally by tier variables.
- Duplicate deliveries are excluded from public-claim samples.
- Legacy duplicate terminal notifications are suppressed.
- Terminal messages contain traceable evidence.
- Successful notification cycles can finalize the global outcome.
- Paper close-all fallback is explicit and freshness-bounded.

## Runtime evidence still required

After redeployment, prove:

- no same-user same-asset delivery inside four hours, including owner/admin;
- exact SOL-style duplicates and near-price BNB-style duplicates are collapsed;
- historical duplicate repair produces the expected dry-run and apply report;
- worker logs a positive `partial_exit_repairs` count where legacy data exists;
- `/performance` displays non-zero TP1/TP2-stopped counts when those lifecycle events exist;
- repeated terminal `sent=0` deferrals stop;
- paper account can close/reset and open a fresh eligible position;
- readiness, outcome coverage and performance-ledger coverage meet configured thresholds.

The validation container lacks Telegram/APScheduler packages and has no external provider/DB access. Tests that import those runtimes, plus provider-network integration tests, must also pass inside the project's `.audit-venv` and Railway image.
