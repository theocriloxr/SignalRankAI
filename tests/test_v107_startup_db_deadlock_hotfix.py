from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _function_source(path: str, name: str) -> str:
    source = _source(path)
    tree = ast.parse(source)
    lines = source.splitlines()
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def test_v107_hotfix_is_carried_forward_by_v108() -> None:
    assert 'default="1.1.0"' in _source("core/version.py")


def test_keyboard_refresh_is_disabled_by_default_and_not_inline() -> None:
    source = _source("signalrank_telegram/bot.py")
    assert 'ACTIVE_SIGNAL_KEYBOARD_REFRESH_ENABLED' in source
    assert '"date"' in source
    assert 'ACTIVE_SIGNAL_KEYBOARD_REFRESH_STARTUP_DELAY_SECONDS' in source
    assert 'refresh_active_signal_keyboards_once()\n    except' not in source
    assert '[keyboard_refresh] startup refresh disabled' in source


def test_keyboard_refresh_snapshots_then_releases_db_before_telegram() -> None:
    source = _function_source(
        "signalrank_telegram/bot.py",
        "refresh_active_signal_keyboards_once",
    )
    assert 'priority="background"' in source
    assert 'label="telegram.keyboard_refresh.snapshot"' in source
    assert '_load_signal_payload' not in source
    assert '_load_signal_engagement_counts' not in source
    assert 'async with bot:' in source
    assert 'bot.edit_message_reply_markup' in source
    # The DB context is confined to the nested snapshot collector, while
    # Telegram calls live in the separate _run coroutine.
    assert 'async def _collect_snapshots' in source
    assert 'async def _refresh_one' in source


def test_outcome_tracker_deferral_is_normal_backpressure() -> None:
    source = _source("engine/realtime_outcome_tracker.py")
    assert 'isinstance(exc, DatabaseWorkDeferred)' in source
    assert '[outcome_tracker] fetch deferred by DB admission controller' in source


def test_startup_summary_reports_worker_only_outcome_ownership() -> None:
    source = _source("railway_main.py")
    assert 'ENGINE_OUTCOME_TRACKER_ENABLED", "0"' in source
    assert 'DISABLED(worker_owned)' in source
    assert 'worker loop is the sole realtime outcome owner' in source


def test_runtime_diagnostics_inputs_are_present_in_docker_image() -> None:
    source = _source(".dockerignore")
    assert '!.env.example' in source
    assert '!docs/' in source
    assert '!docs/**' in source


def test_railway_profiles_disable_keyboard_refresh() -> None:
    for rel in (
        ".env.example",
        "configs/env/railway-staging.env.example",
        "configs/env/railway-hobby-owner-beta.env.example",
    ):
        assert 'ACTIVE_SIGNAL_KEYBOARD_REFRESH_ENABLED=0' in _source(rel), rel

def test_webhook_registration_is_idempotent_and_rate_limit_aware() -> None:
    source = _source("railway_main.py")
    assert 'webhook already registered' in source
    assert 'TELEGRAM_FORCE_WEBHOOK_REREGISTER' in source
    assert 'TELEGRAM_WEBHOOK_SET_MAX_ATTEMPTS' in source
    assert 'retry_after' in source
    assert 'preserving existing webhook' in source

