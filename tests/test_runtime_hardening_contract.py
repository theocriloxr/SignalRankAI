from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_core_uses_canonical_safe_asset_concurrency():
    source = text("engine/core.py")
    assert '"MARKET_FETCH_ASSET_CONCURRENCY"' in source
    assert "effective_asset_concurrency" in source
    assert "min(configured_concurrency, 4)" in source


def test_core_fetches_required_before_optional():
    source = text("engine/core.py")
    required_call = source.index('diagnostic_scope="required"')
    optional_call = source.index('diagnostic_scope="optional"')
    assert required_call < optional_call
    assert "usable_required" in source


def test_zero_candidate_delivery_short_circuits_before_audience_lookup():
    source = text("engine/core.py")
    guard = source.index('if not scored_signals_all:')
    audience = source.index('user_ids = list(get_all_user_ids_compat() or [])', guard)
    assert guard < audience
    between = source[guard:audience]
    assert "[delivery_skipped]" in between
    assert "continue" in between


def test_worker_owned_outcomes_are_not_scheduled_twice():
    source = text("signalrank_telegram/bot.py")
    assert '_worker_outcome_owner = _env_bool("WORKER_OUTCOME_TRACKER_ENABLED", True)' in source
    assert source.count("if not _worker_outcome_owner:") >= 2
    assert "[background_job_ownership]" in source


def test_release_guard_requires_explicit_evidence():
    source = text("core/release_guard.py")
    required = {
        "stale_blocking_enabled": "FRESHNESS_CERTIFICATION_ID",
        "delivery_proof": "DELIVERY_LIFECYCLE_CERTIFICATION_ID",
        "outcome_tracker": "OUTCOME_TRACKER_CERTIFICATION_ID",
        "shadow_tracking": "SHADOW_TRACKING_CERTIFICATION_ID",
        "engine_pulse_integrity": "ENGINE_PULSE_CERTIFICATION_ID",
        "performance_truth": "PERFORMANCE_TRUTH_CERTIFICATION_ID",
        "no_secret_leakage": "SECRET_SCAN_CERTIFICATION_ID",
        "tests_passed": "TEST_CERTIFICATION_ID",
        "ohlc_pipeline": "OHLC_PIPELINE_CERTIFICATION_ID",
        "telegram_delivery_lifecycle": "TELEGRAM_LIFECYCLE_CERTIFICATION_ID",
    }
    for key, certificate in required.items():
        assert f'_evidence(supplied, "{key}", "{certificate}")' in source


def test_safe_env_profiles_have_no_duplicates_or_unsafe_flags():
    from scripts.validate_env_contract import validate

    for relative in (
        "configs/env/hermetic-test.env.example",
        "configs/env/railway-staging.env.example",
        "configs/env/production.env.example",
    ):
        assert validate(ROOT / relative) == []


def test_changed_python_files_parse():
    for relative in (
        "engine/core.py",
        "data/market_data.py",
        "signalrank_telegram/bot.py",
        "core/release_guard.py",
        "scripts/validate_env_contract.py",
    ):
        ast.parse(text(relative), filename=relative)


def test_empty_final_candidates_skip_cooldown_database_reads():
    source = text("engine/core.py")
    empty_guard = source.index('if not final_signals:')
    cooldown = source.index('async def _batch_cooldown_check()', empty_guard)
    between = source[empty_guard:cooldown]
    assert "_maybe_log_heatmap" in between
    assert "continue" in between


def test_threshold_force_uses_boolean_parsing_and_logs_effective_values():
    core_source = text("engine/core.py")
    dedup_source = text("engine/signal_deduplicator.py")
    assert '_env_bool("PREMIUM_SCORE_THRESHOLD_FORCE", False)' in core_source
    assert 'bool((os.getenv("PREMIUM_SCORE_THRESHOLD_FORCE")' not in core_source
    force_block_start = dedup_source.index('os.getenv("PREMIUM_SCORE_THRESHOLD_FORCE")')
    force_block = dedup_source[force_block_start:force_block_start + 320]
    for truthy in ('"1"', '"true"', '"yes"', '"on"', '"y"'):
        assert truthy in force_block
    assert "preserving env thresholds" in core_source


def test_every_empty_asset_is_classified_immediately():
    source = text("engine/core.py")
    assert 'DIAGNOSTIC_HEATMAP_EMPTY_CYCLES", 1' in source
    assert 'heatmap = {"unclassified_pipeline_exit": 1}' in source
    assert 'effective_thresholds={score:%.2f,confluence:%.2f,ml:%.3f}' in source


def test_paystack_recovery_never_occupies_the_critical_db_lane():
    source = text("payments/paystack_events.py")
    recovery = source[source.index("async def recover_paystack_events_once"):source.index("async def paystack_webhook_recovery_loop")]
    assert "priority=DBPriority.BACKGROUND" in recovery
    assert "timeout_seconds=2.0" in recovery


def test_paystack_recovery_retries_quickly_after_background_contention():
    source = text("payments/paystack_events.py")
    loop = source[source.index("async def paystack_webhook_recovery_loop"):]
    assert "except NoncriticalWriteDropped:" in loop
    assert "PAYSTACK_WEBHOOK_BUSY_RETRY_SECONDS" in loop
    assert "sleep_for = min(interval, busy_retry)" in loop


def test_outcome_tracker_skips_reprocessing_already_recorded_tp():
    source = text("engine/realtime_outcome_tracker.py")
    hit = source[source.index("if hit:"):source.index("# Time-stop stale unresolved delivered signals")]
    assert "if target_tp <= prev_tp:" in hit
    assert "await publish_snapshot()" in hit
    assert "return" in hit
    assert "advanced_stages" in hit
    assert "[outcome_tracker] Hit committed:" in hit
    assert "await _set_tp_progress(signal_id, tp_index)" in hit
    assert hit.index("if target_tp <= prev_tp:") < hit.index("[outcome_tracker] Hit committed:")
    progress = source[source.index("def _database_tp_progress"):source.index("@dataclass", source.index("def _database_tp_progress"))]
    assert 'getattr(lifecycle, "highest_tp_hit", 0)' in progress
    cache = source[source.index("async def _get_tp_progress"):source.index("async def _set_tp_progress")]
    assert "state.cache_get" in cache


def test_decomposed_worker_does_not_own_dynamic_instrument_catalogue_by_default():
    source = text("worker/worker.py")
    assert '_discovery_default = not _env_bool("DECOMPOSED_TOPOLOGY_ENABLED", False)' in source
    assert '_env_bool("DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED", _discovery_default)' in source
    assert "DynamicInstrumentDiscovery disabled for decomposed worker" in source


def test_analytics_owns_dynamic_instrument_catalogue_refresh():
    analytics = text("runtime/analytics.py")
    refresh = text("services/instrument_catalogue_refresh.py")
    assert 'DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED' in analytics
    assert 'instrument_catalogue_refresh_loop(stop)' in analytics
    assert 'name="instrument-catalogue-refresh"' in analytics
    assert 'priority=_db_priority()' in refresh
    assert 'return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"' in refresh
    assert 'asyncio.to_thread(discover, top=top)' in refresh
    assert 'await asyncio.wait_for(' in refresh
    assert 'label="analytics.instrument_discovery.persist"' in refresh



def test_web_fanout_retries_background_admission_pressure_without_warning_loop():
    source = text("worker/worker.py")
    section = source[
        source.index("async def _web_signal_fanout_loop"):
        source.index("async def _expiry_loop")
    ]
    assert "NoncriticalWriteDropped" in section
    assert "AnalyticsWorkDeferred" in section
    assert "DatabaseWorkDeferred" in section
    assert "WEB_SIGNAL_FANOUT_DB_BUSY_RETRY_SECONDS" in section
    assert "deferred reason=db_capacity" in section
    assert "deferred reason=db_wait_timeout" in section
    assert "sleep_for = min(" in section


def test_retention_is_staggered_away_from_startup_and_cache_has_provenance():
    retention = text("db/storage_maintenance.py")
    market_data = text("data/market_data.py")
    assert "LEARNING_HISTORY_RETENTION_STARTUP_DELAY_SECONDS" in retention
    assert '"startup_delay_seconds"' in retention
    assert "await asyncio.sleep(startup_delay)" in retention
    assert '"source": "postgres_cache"' in market_data
    assert "_cash_session_reopen_threshold" in market_data


def test_outcome_performance_reconciliation_uses_bounded_user_batch():
    source = text("worker/worker.py")
    block = source[
        source.index("async def _outcome_reconciliation_loop"):
        source.index("async def _adaptive_learning_loop")
    ]
    assert "OUTCOME_PERFORMANCE_RECONCILIATION_USER_LIMIT" in block
    assert '"2"' in block
    assert "limit_users=performance_user_limit" in block

def test_ecosystem_bootstrap_releases_db_between_seed_phases():
    source = text("worker/worker.py")
    block = source[
        source.index("async def _ecosystem_bootstrap_once"):
        source.index("async def _instrument_discovery_loop")
    ]
    assert "WORKER_BOOTSTRAP_PHASE_TIMEOUT_SECONDS" in block
    assert "WORKER_BOOTSTRAP_DB_ADMISSION_TIMEOUT_SECONDS" in block
    assert '("subscriptions", seed_subscription_catalogue)' in block
    assert '("ml", seed_ml_governance)' in block
    assert '("strategies", seed_strategy_registry)' in block
    assert 'label=f"worker.ecosystem_bootstrap.{phase_name}"' in block
    assert "await asyncio.wait_for(" in block
    assert "await session.commit()" in block
    assert 'label="worker.ecosystem_bootstrap"' not in block

def test_subscription_catalogue_bootstrap_batches_db_round_trips():
    source = text("db/ecosystem_bootstrap.py")
    block = source[
        source.index("async def seed_subscription_catalogue"):
        source.index("async def seed_ml_governance")
    ]
    assert "product_params = [" in block
    assert "price_params = [" in block
    assert "entitlement_params: list[dict[str, Any]] = []" in block
    assert "await session.execute(close_previous_price, price_params)" in block
    assert "await session.execute(upsert_release_price, price_params)" in block
    assert "await session.execute(entitlement_upsert, entitlement_params)" in block
    assert "entitlement_rows = len(entitlement_params)" in block
    assert 'bindparam("product_id", type_=String(64))' in block
    assert 'bindparam("price_kobo", type_=BigInteger())' in block



def test_frontdoor_readiness_uses_live_engine_cycle_not_hourly_admin_pulse():
    railway = text("railway_main.py")
    engine = text("engine/core.py")
    assert 'state.get_sync("engine:last_cycle")' in railway
    assert 'ENGINE_RUNTIME_HEARTBEAT_MAX_AGE_SECONDS' in railway
    assert '"engine_runtime"' in railway
    assert 'READINESS_REQUIRE_ENGINE_PULSE", False' in railway
    assert '"git_sha": str(os.getenv("RAILWAY_GIT_COMMIT_SHA")' in engine
    assert '"deployment_id": str(os.getenv("RAILWAY_DEPLOYMENT_ID")' in engine


def test_learning_retention_never_mutates_legacy_ml_rejected_view():
    retention = text("db/storage_maintenance.py")
    assert "DELETE FROM ml_rejected_signals" not in retention
    assert "SELECT id FROM ml_rejected_signals" not in retention
    assert "DELETE FROM decision_log AS target" in retention
    assert "COALESCE(meta->>'layer', '') = 'ml'" in retention
    assert "REJECTION_TRACKED_RETENTION_DAYS" in retention
    assert "REJECTION_UNTRACKED_RETENTION_DAYS" in retention
    assert "NOT (" in retention
