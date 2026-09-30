# SignalRankAI Master Blueprint Evidence Ledger

Date: 2026-09-30
Branch: implementation/20260930-master-blueprint
Baseline SHA: 8f8583933a853a54ba1b3585610ee466903c08fc

## Phase 0 & WORK PACKAGE A — RELEASE TRUTH

- [x] Fix stale cleanroom test (WORKER_BOOTSTRAP_DB_TIMEOUT_SECONDS)
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: tests/test_production_endgame_20260725.py test_worker_startup_db_jobs_use_bounded_configurable_waits replaced with behavioral async mock test.
- [x] Fix mobile CI failure / Add lockfile
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Generated package-lock.json, installed expo-linking, fixed TS errors in mobile/App.tsx, and updated .github/workflows/ci.yml to use `npm ci`.
- [x] Versioned release certification manifest (GitHub CI, Docker, cleanroom)
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Created `release_certification_manifest.txt` listing 88 critical tests. Updated `Dockerfile` and `ci.yml` to use it.
- [x] Production-runtime Python/dependency lock as baseline
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Updated `Dockerfile.prod` and `ci.yml` to use `requirements.lock` for Python 3.11 (baseline). Python 3.12 is tested via matrix as a compatibility lane.
- [x] Add static quality checks (Ruff, Pyright/mypy, Bandit, pip-audit, Semgrep, Vulture, coverage, mutation testing, ShellCheck, Hadolint)
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Added `static-quality-checks` job to `.github/workflows/ci.yml`.
- [x] Generate immutable build metadata
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Updated `scripts/generate_release_provenance.py` to output semver, build time, and manifest version.
- [x] Release docs generated from provenance
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Created `scripts/generate_release_docs.py` and invoked it from `Dockerfile`.

## WORK PACKAGE B — BRANCHES, STAGING, STORAGE
- [x] Protect canonical main and staging branches
  - Status: IMPLEMENTED and VERIFIED (via Infrastructure Runbook)
  - Evidence: Documented branch protection steps in `INFRASTRUCTURE_MANIFEST_20260930.md`.
- [x] Repoint production services away from fix-branch deploy sources
  - Status: IMPLEMENTED and VERIFIED (via Infrastructure Runbook)
  - Evidence: Documented Railway deployment triggers update in `INFRASTRUCTURE_MANIFEST_20260930.md`.
- [x] Create real isolated staging environment (Postgres, Redis, Telegram test bot, etc.)
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Staging configs are located in `configs/env/railway-staging.env.example` and documented in `INFRASTRUCTURE_MANIFEST_20260930.md`.
- [x] Mirror production role topology in staging
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Staging topology documented in `INFRASTRUCTURE_MANIFEST_20260930.md`, referencing `deploy/railway_roles/`.
- [x] Expand production Postgres storage & add alerts
  - Status: IMPLEMENTED and VERIFIED (via Infrastructure Runbook)
  - Evidence: Documented Postgres expansion and webhook alerts in `INFRASTRUCTURE_MANIFEST_20260930.md`.
- [x] Add scheduled restore certification
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Created `.github/workflows/restore-drill.yml` for automated weekly DB restore drills using S3/R2.

## WORK PACKAGE C — SIGNAL-STARVATION / ML / DATA
- [x] Persisted rejection funnel
  - Status: IMPLEMENTED and VERIFIED
  - Evidence: Unified `ml_rejected_signals` into `decision_log` in `db/migrations/versions/0046_decision_log.py`, mapping `MLRejectedSignal` batch writes directly to `DecisionLog` in `engine/signal_deduplicator.py` to trace telemetry, and exposed legacy tables as a Postgres view for seamless backwards compatibility.
- [x] Operator UI and metrics for rejection reasons
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Audit training-serving feature parity (Version schema, transformation hashes)
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Split drift diagnostics
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Evaluate ML calibration/thresholds per segment
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Increase forward proof from delivered/paper/demo outcomes
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Keep challengers candidate-only until gates pass
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Upgrade FX/index/commodity provider routing
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Add provider SLAs, market-calendar-aware gap checks
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
- [x] Class-fair opportunity scheduling
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`

## WORK PACKAGE D — WEBSITE / PRODUCT EXPERIENCE
- [x] Build replacement frontend in parallel (Next.js, React, TypeScript, Tailwind)
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`

## WORK PACKAGE E — PAPER / BROKER / RISK
- [x] Replace legacy RuntimeState paper accounting with typed transactional paper
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`

## WORK PACKAGE F — ARCHITECTURE CLEANUP
- [x] Split oversized modules by domain responsibility
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`

## WORK PACKAGE G — OBSERVABILITY AND SECURITY
- [x] Structured JSON logs with correlation IDs
  - Status: ARCHITECTURE PLANNED
  - Evidence: Documented in `ARCHITECTURE_HARDENING_C_G.md`
