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
    for key in (
        "stale_blocking_enabled",
        "delivery_proof",
        "outcome_tracker",
        "performance_truth",
        "no_secret_leakage",
        "tests_passed",
        "ohlc_pipeline",
        "telegram_delivery_lifecycle",
    ):
        assert f'supplied.get("{key}", False)' in source


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
