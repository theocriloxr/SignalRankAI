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
    assert 'in {"1", "true", "yes", "on", "y"}' in dedup_source
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
