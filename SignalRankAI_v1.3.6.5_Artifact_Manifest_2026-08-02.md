# SignalRankAI v1.3.6.5 Artifact Manifest

Generated: 2026-08-02T15:26:43.274874+00:00
Base release: v1.3.6.4
Release: v1.3.6.5
Fingerprint: `v1.3.6.5-production-integrity-hardening-20260802`

## Deliverables

- `SignalRankAI_v1.3.6.5_PRODUCTION_INTEGRITY_PROFILE_DISCOVERY_HARDENING_RELEASE.zip` — clean full source release.
- `SignalRankAI_v1.3.6.5_HOTFIX_OVERLAY.zip` — changed/new files plus PowerShell installer.
- `SignalRankAI_v1.3.6.5_Production_Integrity_Hardening.patch` — unified source patch from v1.3.6.4.
- `SignalRankAI_v1.3.6.5_SHA256SUMS.txt` — external artifact checksums.
- `SignalRankAI_v1.3.6.5_Release_Notes.md`.
- `SignalRankAI_v1.3.6.5_Deployment_Guide.md`.
- `SignalRankAI_v1.3.6.5_Certification_Report.md`.
- `SignalRankAI_v1.3.6.5_Railway.env.example`.

## Source delta

- Changed/new files: 79
- Modified from v1.3.6.4: 62
- New in v1.3.6.5: 17
- Deleted: 0

### Modified

- `.env.example`
- `RELEASE_FINGERPRINT.txt`
- `core/financial_activation.py`
- `core/paper_trading_service.py`
- `core/release_guard.py`
- `core/tier_policy.py`
- `core/version.py`
- `data/pair_discovery.py`
- `db/models.py`
- `db/pg_features.py`
- `db/repository.py`
- `engine/admin_pulse.py`
- `engine/core.py`
- `engine/ml.py`
- `engine/realtime_outcome_tracker.py`
- `engine/risk_sizer.py`
- `engine/scoring.py`
- `engine/shadow_outcome_worker.py`
- `engine/signal_lifecycle.py`
- `engine/signal_metrics.py`
- `ml/model_registry.py`
- `ml/train_model.py`
- `railway_main.py`
- `requirements/callback_registry.yaml`
- `requirements/command_registry.yaml`
- `requirements/environment_registry.yaml`
- `requirements/feature_flags.yaml`
- `requirements/legacy_disposition.json`
- `scripts/verify_v130_production_cutover.py`
- `scripts/verify_v136_railway_performance_decomposition.py`
- `services/asset_position_manager.py`
- `services/asset_registry.py`
- `services/broker_signal_router.py`
- `services/bybit_signal_router.py`
- `services/execution_quota.py`
- `services/mt5_signal_router.py`
- `services/opportunity_engine.py`
- `services/performance_ledger.py`
- `services/user_intelligence.py`
- `signalrank_telegram/bot.py`
- `signalrank_telegram/command_catalog.py`
- `signalrank_telegram/commands.py`
- `signalrank_telegram/extended_commands.py`
- `signalrank_telegram/formatter.py`
- `signalrank_telegram/tier_signal_formatter.py`
- `signalrank_telegram/user_prefs.py`
- `tests/test_broker_execution_p0.py`
- `tests/test_canonical_broker_entrypoints.py`
- `tests/test_production_endgame_20260725.py`
- `tests/test_runtime_hardening_contract.py`
- `tests/test_v104_runtime_schema_hotfix.py`
- `tests/test_v106_delivery_db_hotfix.py`
- `tests/test_v123_log_driven_hotfix.py`
- `tests/test_v125_live_paystack_delivery_hotfix.py`
- `tests/test_v127_outcome_price_production.py`
- `tests/test_v128_outcome_perf_readiness_hotfix.py`
- `tests/test_v129_lifecycle_profile_observability_hotfix.py`
- `tests/test_v130_production_cutover_outcome_recovery.py`
- `tests/test_v131_live_financial_activation.py`
- `tests/test_v132_auto_delivery_callbacks_monitor.py`
- `tests/test_v1364_runtime_stability_hotfix.py`
- `worker/worker.py`

### New

- `SignalRankAI_v1.3.6.5_Artifact_Manifest_2026-08-02.md`
- `SignalRankAI_v1.3.6.5_Certification_Report.md`
- `SignalRankAI_v1.3.6.5_Deployment_Guide.md`
- `SignalRankAI_v1.3.6.5_Railway.env.example`
- `SignalRankAI_v1.3.6.5_Release_Notes.md`
- `apply_signalrank_v1.3.6.5_hotfix.ps1`
- `core/live_execution_integrity.py`
- `core/outcome_ordering.py`
- `core/production_integrity.py`
- `core/signal_quality_gate.py`
- `db/migrations/versions/0034_production_integrity.py`
- `scripts/verify_v1365_production_integrity.py`
- `services/outcome_reconciliation.py`
- `services/profile_demand.py`
- `tests/test_v1365_production_integrity.py`
- `tests/test_v1365_production_integrity_profile_routing.py`
- `v1.3.6.5-overlay-manifest.txt`

## Validation summary

- Production-focused matrix: 144 passed.
- Dependency-independent broad matrix: 405 passed, 1 skipped.
- Integrity verifier: PASS.
- Schema audit: PASS; 34 revisions; head `0034_production_integrity`.
- Python compilation: 818 files; zero errors.
- Governance registry: current.
- Live activation: intentionally blocked until post-deployment certification.

## Safety boundary

The release does not prove or guarantee a 60% win rate. Public performance and probability statements remain fail-closed until statistical, reconciliation and calibration gates pass. Live and copy execution remain disabled until their independent evidence contracts pass.
