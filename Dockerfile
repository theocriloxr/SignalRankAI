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
RUN python -m compileall -q engine db data worker services ml \
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
      tests/test_phase4_pass2_db_priority_and_command_speed.py::test_dedicated_analytics_role_cannot_be_pinned_to_one_session \
      tests/test_phase4_pass1_quote_contract.py::test_twelvedata_quote_falls_back_to_timestamped_one_minute_bar \
      tests/test_production_endgame_20260725.py::test_current_gemini_review_request_avoids_legacy_sampling_knobs \
      tests/test_production_endgame_20260725.py::test_metaapi_discovery_uses_canonical_account_aliases \
      tests/test_deployment_schema_completion_v151.py::test_production_migration_fast_path_skips_backup_and_lock_at_head \
      tests/test_deployment_schema_completion_v151.py::test_production_migration_lock_wait_is_bounded_and_nonblocking

# Ensure start script is executable and use it as entrypoint so migrations/run-time
# setup happens when the container starts (not during image build).
RUN chmod +x ./start.sh || true

EXPOSE 8080

# Use the start script which runs migrations and then starts the appropriate service
ENTRYPOINT ["/bin/bash", "./start.sh"]
