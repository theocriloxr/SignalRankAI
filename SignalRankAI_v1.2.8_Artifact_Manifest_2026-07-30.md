# SignalRankAI v1.2.8 Artifact Manifest

Date: 2026-07-30  
Release fingerprint: `v1.2.8-outcome-perf-readiness-hotfix-20260730`  
Migration head: `0027_launch_paper_trading`

## Primary release

`SignalRankAI_v1.2.8_OUTCOME_PERFORMANCE_READINESS_HOTFIX_RELEASE.zip`

- Flat root-level deployment archive.
- Preserves the complete v1.2.7 outcome, price, adaptive database and production-gate release.
- Adds the outcome user-performance SQLAlchemy fix and direct Railway Prometheus route.
- Contains no deployment secrets.

## Supporting artifacts

- `SignalRankAI_v1.2.8_Outcome_Performance_Readiness_Hotfix.patch`
- `SignalRankAI_v1.2.8_Railway_Full_System_Live_Paystack_Staging.env.example`
- `SignalRankAI_v1.2.8_Railway_Production_Launch.env.example`
- `SignalRankAI_v1.2.8_Outcome_Performance_Readiness_Hotfix_Release_Notes.md`
- `SignalRankAI_v1.2.8_Certification_Report_2026-07-30.md`
- `SignalRankAI_v1.2.8_Production_Launch_Gate_Checklist.md`
- `SignalRankAI_v1.2.8_SHA256SUMS.txt`

## Verification summary

- Tracked Python compilation: PASS (`749` files, `0` failures)
- Schema audit: PASS
- Alembic revisions: `27`
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: `9/9` PASS
- Architecture smoke: PASS
- Legacy DB session call sites: `0`
- Secret scan: `0` findings
- v1.2.5, v1.2.6, v1.2.7 and v1.2.8 verifiers: PASS
- Focused hotfix tests: `22` passed
- Broader selected tests: `92` passed, `2` dependency-bound assertions deselected

## Runtime proof status

Local code certification is complete. Railway runtime proof is still required for the dependency-complete Telegram/scheduler paths, direct Prometheus response and absence of the original `func` NameError under live staging load.
