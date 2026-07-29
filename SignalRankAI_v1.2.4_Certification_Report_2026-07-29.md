# SignalRankAI v1.2.4 Certification Report

Date: 2026-07-29
Release fingerprint: `v1.2.4-runtime-admission-advisory-pipeline-20260729`

## Local certification

- Root-level source compilation: PASS
- Schema audit: PASS
- Alembic revisions: 27
- Sole migration head: `0027_launch_paper_trading`
- Production-readiness checks: 8/8 PASS
- DB legacy session call audit: 0 call sites
- Architecture smoke: PASS
- Secret scan: 0 findings
- v1.2.4 verifier: PASS
- Focused regression suite: 60 passed

## Broader test-suite boundary

The complete test collection could not run in this local container because the
container does not have `python-telegram-bot` and APScheduler installed. Seven
collection modules were blocked for that reason. Both dependencies are declared in
`requirements.txt` and were present in the supplied Railway runtime logs.

## Runtime evidence required after deployment

Expected startup markers:

- `[boot] SignalRankAI v1.2.4`
- `release=v1.2.4-runtime-admission-advisory-pipeline-20260729`
- `[startup_safety] requested=1 acknowledgement_valid=1 full_system_test_enabled=1 environment=staging`
- `[worker] AdaptiveCandleCapture started`
- `[worker] PaperTradingWorker started`
- `[paper_worker] started`

Expected workflow proof:

- at least one `final_signals>0`
- at least one stored signal
- delivery proof reaching `CONFIRMED`
- `[paper_auto_open]`
- eventual `[paper_auto_close]` when TP/SL is reached

Paystack test proof remains unavailable until test credentials are configured.
