# SignalRankAI v1.3.6.7 Artifact Manifest

Date: 2026-08-02

Fingerprint: `v1.3.6.7-integrity-accounting-dedup-hotfix-20260802`

Database head: `0034_production_integrity`

## Validation

- v1.3.6.7 integrity/accounting verifier: PASS
- inherited v1.3.6.6 and v1.3.6.5 verifiers: PASS
- schema audit: PASS
- V7 governance generation/check: PASS
- Python compilation: PASS
- focused regression matrix: 40 passed
- dependency-independent broad matrix: 822 passed, 1 skipped
- full Telegram/APScheduler/provider integration suite: must run in the project `.audit-venv` and Railway image

## Changed and added project files

- `.env.example`
- `RELEASE_FINGERPRINT.txt`
- `SignalRankAI_v1.3.6.7_Certification_Report.md`
- `SignalRankAI_v1.3.6.7_Deployment_Guide.md`
- `SignalRankAI_v1.3.6.7_Railway.env.example`
- `SignalRankAI_v1.3.6.7_Release_Notes.md`
- `core/outcome_ordering.py`
- `core/paper_trading_service.py`
- `core/partial_exit_accounting.py`
- `core/production_integrity.py`
- `core/signal_lifecycle.py`
- `core/version.py`
- `db/pg_features.py`
- `db/repository.py`
- `engine/realtime_outcome_tracker.py`
- `requirements/callback_registry.yaml`
- `requirements/command_registry.yaml`
- `requirements/environment_registry.yaml`
- `requirements/feature_flags.yaml`
- `requirements/legacy_disposition.json`
- `scripts/repair_active_signal_duplicates.py`
- `scripts/verify_v130_production_cutover.py`
- `scripts/verify_v1365_production_integrity.py`
- `scripts/verify_v1366_runtime_certification_hotfix.py`
- `scripts/verify_v1367_integrity_accounting_hotfix.py`
- `scripts/verify_v136_railway_performance_decomposition.py`
- `services/asset_repeat_policy.py`
- `services/performance_ledger.py`
- `signalrank_telegram/bot.py`
- `signalrank_telegram/commands.py`
- `signalrank_telegram/extended_commands.py`
- `tests/test_asset_repeat_policy.py`
- `tests/test_timezone_and_performance_v2.py`
- `tests/test_v123_log_driven_hotfix.py`
- `tests/test_v125_live_paystack_delivery_hotfix.py`
- `tests/test_v127_outcome_price_production.py`
- `tests/test_v128_outcome_perf_readiness_hotfix.py`
- `tests/test_v129_lifecycle_profile_observability_hotfix.py`
- `tests/test_v130_production_cutover_outcome_recovery.py`
- `tests/test_v131_live_financial_activation.py`
- `tests/test_v132_auto_delivery_callbacks_monitor.py`
- `tests/test_v1364_runtime_stability_hotfix.py`
- `tests/test_v1367_integrity_accounting_hotfix.py`
- `worker/worker.py`

## Safety state

- Live execution: disabled pending runtime certification
- Copy trading: disabled pending runtime certification
- Public performance marketing: disabled pending evidence gates
- Payments-public: disabled during staging certification
