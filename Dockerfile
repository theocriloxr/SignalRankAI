FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by some Python packages (e.g. psycopg2)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends gcc libpq-dev \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt ./

# Ensure pip/tools are up-to-date and install Python deps
RUN python -m pip install --upgrade pip setuptools wheel \
	&& pip install -r requirements.txt

# Copy application code
COPY . .

# Release-critical regression gate. GitHub-hosted CI can be unavailable before a
# runner starts; these deterministic tests therefore also execute in the image
# build and must pass before Railway can deploy the artifact.
RUN python -m compileall -q engine db data worker services ml signalrank_telegram \
    && python -m pytest -q \
      tests/test_provider_backed_asset_discovery.py \
      tests/test_cpu_only_xgboost_dependency.py \
      tests/test_ml_learning_runtime_v135.py::test_analytics_owned_workers_share_analytics_priority_lane \
      tests/test_ml_learning_runtime_v135.py::test_dedicated_analytics_ml_uses_analytics_priority_and_bounded_wait \
      tests/test_ml_learning_runtime_v135.py::test_ml_candle_hydration_is_bounded_to_training_window \
      tests/test_ml_learning_runtime_v135.py::test_ml_training_is_nonblocking_and_multisource \
      tests/test_railway_runtime_incident_fixes.py::test_signal_insert_reuses_the_exact_active_unique_index_bucket \
      tests/test_railway_runtime_incident_fixes.py::test_both_signal_persistence_paths_serialize_database_unique_bucket \
      tests/test_runtime_hardening_contract.py::test_paystack_recovery_never_occupies_the_critical_db_lane \
      tests/test_runtime_hardening_contract.py::test_paystack_recovery_retries_quickly_after_background_contention \
      tests/test_runtime_hardening_contract.py::test_outcome_tracker_skips_reprocessing_already_recorded_tp \
      tests/test_runtime_hardening_contract.py::test_decomposed_worker_does_not_own_dynamic_instrument_catalogue_by_default \
      tests/test_runtime_hardening_contract.py::test_analytics_owns_dynamic_instrument_catalogue_refresh \
      tests/test_phase4_pass2_db_priority_and_command_speed.py::test_dedicated_analytics_role_cannot_be_pinned_to_one_session \
      tests/test_phase4_pass1_quote_contract.py::test_twelvedata_quote_falls_back_to_timestamped_one_minute_bar \
      tests/test_production_endgame_20260725.py::test_engine_uses_provider_neutral_ai_router_instead_of_raw_gemini_http \
      tests/test_production_endgame_20260725.py::test_metaapi_discovery_uses_canonical_account_aliases \
      tests/test_production_endgame_20260725.py::test_engine_metadata_reads_wait_boundedly_under_db_contention \
      tests/test_production_endgame_20260725.py::test_engine_required_metadata_uses_protected_lane_and_outer_timeout_exceeds_db_wait \
      tests/test_v1366_runtime_certification_hotfix.py::test_deployed_ml_quality_gate_accepts_imbalanced_candidate_that_beats_utility_gates \
      tests/test_v1366_runtime_certification_hotfix.py::test_deployed_ml_quality_gate_accepts_strong_pr_auc_lift_on_imbalanced_data \
      tests/test_v1366_runtime_certification_hotfix.py::test_deployed_ml_quality_gate_rejects_weak_pr_auc_lift \
      tests/test_v1366_runtime_certification_hotfix.py::test_deployed_ml_quality_gate_still_rejects_majority_collapse \
      tests/test_v1366_runtime_certification_hotfix.py::test_class_balance_scale_is_bounded_for_minority_positive_class \
      tests/test_v1366_runtime_certification_hotfix.py::test_classification_threshold_is_selected_on_imbalanced_calibration_window \
      tests/test_v1366_runtime_certification_hotfix.py::test_threshold_selection_prefers_positive_expected_r_over_low_balanced_accuracy_cutoff \
      tests/test_v1366_runtime_certification_hotfix.py::test_training_uses_fit_window_balance_and_calibration_threshold_only \
      tests/test_deployment_schema_completion_v151.py::test_production_migration_fast_path_skips_backup_and_lock_at_head \
      tests/test_deployment_schema_completion_v151.py::test_production_migration_lock_wait_is_bounded_and_nonblocking \
      tests/test_openai_ai_provider.py \
      tests/test_ai_review_router_consensus.py \
      tests/test_ai_governance_hardening.py \
      tests/test_ml_calibration_audit.py \
      tests/test_ml_serving_threshold_governance.py \
      tests/test_ml_registry.py \
      tests/test_ml_strict_schema.py \
      tests/test_ml_retrain_governance.py \
      tests/test_ml_fail_closed_availability.py \
      tests/test_ml_feature_contract.py \
      tests/test_ml_training_query_timeout.py \
      tests/test_ml_training_dataset_timeout.py \
      tests/test_ml_durable_artifact_sync.py \
      tests/test_ml_shadow_learning_labels.py \
      tests/test_ml_artifact_store_timeout.py \
      tests/test_startup_selfcheck_secret_redaction.py \
      tests/test_web_first_signup_contract.py \
      tests/test_cross_channel_profile_parity.py \
      tests/test_release_source_and_domain_bridge.py \
      tests/test_production_operations_package.py \
    && python scripts/production_readiness_check.py

# Ensure start script is executable and use it as entrypoint so migrations/run-time
# setup happens when the container starts (not during image build).
RUN chmod +x ./start.sh || true

EXPOSE 8080

# Use the start script which runs migrations and then starts the appropriate service
ENTRYPOINT ["/bin/bash", "./start.sh"]
