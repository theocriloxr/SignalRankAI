# SignalRankAI Final Local Completion Report — 26 July 2026

## Executive verdict

Code release commit: `11356c6fdcbd961b05e21263c865eb69527c7bcd`

**Status: CODE_COMPLETE_BUT_LIVE_PROOF_PENDING** for the locally verifiable advisory, paper, demo-gated and production-operations code scope.

The repository has been directly repaired, integrated and regression-tested. The release archive is generated from the final committed tree after the evidence checkpoint is recorded. Local evidence does not prove Railway staging, Telegram network delivery, live provider data, Paystack test reconciliation, MetaApi demo orders, a natural same-signal lifecycle, or the 24–72 hour soak. Public payments, real payouts, copy trading and real execution remain disabled by default.

## Major completion work

- Preserved one canonical FastAPI Railway monolith with one Uvicorn worker.
- Hardened `start.sh` with `set -euo pipefail`, explicit one-worker startup, controlled migrations, safe dotenv opt-in and proper `exec` signal propagation.
- Increased Railway healthcheck cold-start allowance to 300 seconds.
- Fixed the local Railway simulation to accept the canonical liveness contract and authenticate Telegram webhook requests.
- Fixed post-deploy smoke readiness semantics and Telegram webhook secret handling.
- Hardened live-evidence tooling to require two distinct Redis services, verify `/healthz` and `/readyz`, and avoid printing exception messages that can contain secrets.
- Removed duplicate environment keys and added a repository-wide env-profile regression test.
- Canonicalised Telegram-to-broker routing, broker ledger persistence, execution consent, quote/spec/account sizing, quota reservation, idempotency and fail-closed behaviour.
- Removed direct/unsafe Telegram broker paths and fallback `0.01` lot behaviour.
- Hardened native MT5 constraints, MetaApi/demo routing, Smart DCA and broker queue behaviour.
- Implemented proof-backed four-hour per-user same-asset delivery protection.
- Added provider catalogues/adapters/certification for public and keyed provider families.
- Added runtime configuration snapshots, provider certification, repository proof manifest and complete local orchestration scripts.
- Added fail-closed engine gates, delivery/outcome truth controls, rejection telemetry and environment profiles.
- Removed runtime `datetime.utcnow()` usage in favour of shared UTC helpers.
- Fixed token-rotation tests so an unauthenticated `401` is never accepted as successful rotation.
- Fixed the remaining test resource warning.
- Made the proof manifest deterministic by excluding its generated outputs and runtime artefacts.

## Final local verification

The final standalone suite completed successfully:

```text
717 passed, 1 skipped, 0 failed in 20.70s
```

Command:

```bash
PYTHONPATH=/mnt/data/sra_test_stubs:. \
SIGNALRANK_TEST_PYDEPS=/mnt/data/sra_test_stubs \
SIGNALRANK_DISABLE_BACKGROUND_THREADS=1 \
pytest -q
```

Complete-system command:

```bash
python scripts/run_complete_system_test.py \
  --full \
  --pytest-batches 20 \
  --output-dir artifacts/complete-system-test-final

# Resume safely when an execution environment imposes a short command window:
python scripts/run_complete_system_test.py \
  --full \
  --pytest-batches 20 \
  --resume \
  --output-dir artifacts/complete-system-test-final
```

Verified orchestration gates include:

- Python compileall.
- Environment profile contracts.
- One Alembic head with 21 revisions.
- Architecture smoke.
- Zero legacy DB-session API call sites.
- Governance validation.
- Secret scan.
- Production readiness checks.
- Runtime config snapshot.
- Actual local `railway_main:app` startup and authenticated webhook ingress.
- 100,000-user fan-out planning.
- Provider adapter/fixture certification.
- Full pytest suite.
- Full pytest suite split into 20 deterministic bounded batches: 717 passed, 1 skipped, 0 failed.
- Resumable progress state and final machine-readable PASS report.

## Coverage and unavailable quality tools

The final repository-wide coverage run reports 43% statements, 24% branches and 39% combined coverage. This includes a large legacy/compatibility surface and does not meet the aspirational 95% statement/90% branch target in the exhaustive prompt. Coverage must not be misrepresented.

The execution image did not contain Ruff, Mypy/Pyright, Bandit, pip-audit, Semgrep, Hypothesis or a mutation framework. Built-in compile, architecture, schema, secret, environment, invariant and security regression checks passed, but unavailable third-party gates are not claimed.

## Provider evidence

All catalogued providers have implementation/configuration status and fixture/import certification. No provider is represented as live-certified. Outbound DNS was unavailable in the execution container, and keyed credentials were not supplied.

## Live blockers

See `docs/PERMISSION_AND_EXTERNAL_BLOCKER_REGISTER.md`. Required next inputs include:

- Railway staging deployment permission.
- PostgreSQL/PgBouncer.
- Distinct RedisState and RedisDelivery.
- Dedicated Telegram test bot, secret and test chats.
- Selected provider keys.
- TradingView test secret.
- Paystack test keys.
- MetaApi demo account.
- Current subscription prices and retention policy.

## Safe Railway deployment sequence

1. Back up the database and Railway variables.
2. Create PostgreSQL, RedisState and RedisDelivery services.
3. Apply a safe Railway env profile and sealed secrets.
4. Deploy with `bash start.sh` and one replica.
5. Enable migration for one controlled deployment only (`AUTO_MIGRATE=1` or `RUN_DB_MIGRATIONS_AT_BOOT=true`, according to the chosen deployment path).
6. Confirm migration head `0021_runtime_truth_hardening`.
7. Disable automatic migration and redeploy.
8. Verify `/livez`, `/healthz`, `/readyz`, PostgreSQL and both Redis services.
9. Run `scripts/post_deploy_smoke.py` with the webhook secret.
10. Run `scripts/live_production_evidence.py` with live provider smoke enabled.
11. Complete Telegram command/button, all-profile/tier, all-enabled-asset, restart and Redis-recovery tests.
12. Prove one natural signal through delivery, active message, entry and terminal outcome.
13. Complete a 24–72 hour owner-only soak.
14. Expand asset classes and users only after each stage passes.

## Release boundary

This package is suitable for Railway staging and controlled owner verification. It is not evidence of public/paid/real-execution approval.
