# SignalRankAI v1.3.0 Artifact Manifest

Release date: 2026-07-30  
Fingerprint: `v1.3.0-production-cutover-outcome-recovery-20260730`

## Inventory

- Total files: 1074
- Python files: 754
- Files changed from v1.2.9: 28
- Files added from v1.2.9: 10
- Files removed from v1.2.9: 0
- Alembic revisions: 28
- Sole migration head: `0028_outcome_projection_guard`

## Changed files

- `core/version.py`
- `data/market_data.py`
- `data/providers.py`
- `db/models.py`
- `db/pg_features.py`
- `engine/correlation_filter.py`
- `railway_main.py`
- `requirements/callback_registry.yaml`
- `requirements/command_registry.yaml`
- `requirements/environment_registry.yaml`
- `requirements/legacy_disposition.json`
- `runtime_safety.py`
- `scripts/deployment_diagnostics.py`
- `scripts/schema_audit.py`
- `scripts/verify_v125_log_fixes.py`
- `scripts/verify_v126_callback_outcome_recovery.py`
- `scripts/verify_v127_outcome_price_production.py`
- `scripts/verify_v128_outcome_perf_readiness.py`
- `scripts/verify_v129_lifecycle_profile_observability.py`
- `tests/test_production_endgame_20260725.py`
- `tests/test_signal_lock_contract.py`
- `tests/test_stale_learning_multiservice.py`
- `tests/test_v104_runtime_schema_hotfix.py`
- `tests/test_v123_log_driven_hotfix.py`
- `tests/test_v125_live_paystack_delivery_hotfix.py`
- `tests/test_v127_outcome_price_production.py`
- `tests/test_v128_outcome_perf_readiness_hotfix.py`
- `tests/test_v129_lifecycle_profile_observability_hotfix.py`

## Added files

- `SignalRankAI_v1.3.0_Artifact_Manifest_2026-07-30.md`
- `SignalRankAI_v1.3.0_Certification_Report_2026-07-30.md`
- `SignalRankAI_v1.3.0_Post_Deploy_Verification.sql`
- `SignalRankAI_v1.3.0_Production_Cutover_Release_Notes.md`
- `SignalRankAI_v1.3.0_Production_Launch_Gate_Checklist.md`
- `SignalRankAI_v1.3.0_Railway_Full_System_Live_Paystack_Staging.env.example`
- `SignalRankAI_v1.3.0_Railway_Production_Launch.env.example`
- `db/migrations/versions/0028_outcome_projection_guard.py`
- `scripts/verify_v130_production_cutover.py`
- `tests/test_v130_production_cutover_outcome_recovery.py`

## Certification summary

- Focused production/outcome suite: 126 passed.
- Dependency-free repository suite: 480 passed, 1 skipped.
- Production readiness: 9/9 passed.
- Schema audit: passed.
- Architecture smoke: passed.
- Legacy DB session calls: 0.
- Secret scan findings: 0.
- Python compilation: 754 files, 0 failures.
- Compatibility verifiers v1.2.5 through v1.3.0: passed.

## External-runtime boundary

Seven test modules require `python-telegram-bot` and/or APScheduler. Both are declared in `requirements.txt`, but the local package index could not install them. Railway runtime proof remains mandatory for those paths.
