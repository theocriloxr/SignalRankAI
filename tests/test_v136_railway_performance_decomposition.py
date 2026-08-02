from __future__ import annotations

from pathlib import Path

import pytest

from runtime.roles import (
    RunMode,
    parse_run_mode,
    process_ownership,
    scheduler_ownership,
)


def test_frontdoor_is_a_first_class_fail_closed_role() -> None:
    assert parse_run_mode("frontdoor") is RunMode.FRONTDOOR
    assert parse_run_mode("front-door") is RunMode.FRONTDOOR
    assert parse_run_mode("webhook") is RunMode.FRONTDOOR

    ownership = process_ownership(
        "frontdoor",
        {
            "DECOMPOSED_TOPOLOGY_ENABLED": "1",
            # Stale monolith variables must never re-enable heavy loops.
            "RUN_ENGINE_LOOP": "1",
            "RUN_WORKER_LOOP": "1",
        },
    )
    assert ownership.http is True
    assert ownership.telegram is True
    assert ownership.scheduler is True
    assert ownership.engine is False
    assert ownership.worker is False
    assert ownership.decomposed is True


def test_decomposed_topology_rejects_hidden_monolith() -> None:
    with pytest.raises(ValueError, match="forbids RUN_MODE=all"):
        process_ownership(
            "all",
            {"DECOMPOSED_TOPOLOGY_ENABLED": "1"},
        )


def test_frontdoor_can_own_the_existing_scheduler_during_first_split() -> None:
    ownership = scheduler_ownership(
        {"RUN_MODE": "frontdoor", "SCHEDULER_OWNER": "monolith"}
    )
    assert ownership.allows(RunMode.FRONTDOOR)
    assert not ownership.allows(RunMode.ENGINE)


def test_dedicated_roles_skip_unnecessary_startup_work_by_default(monkeypatch) -> None:
    import main

    monkeypatch.delenv("STARTUP_OPS_ENABLED", raising=False)
    monkeypatch.delenv("STARTUP_DATA_SELFCHECK_ENABLED", raising=False)

    assert main._startup_ops_enabled("frontdoor") is False
    assert main._startup_ops_enabled("engine") is False
    assert main._startup_ops_enabled("worker") is False
    assert main._startup_data_selfcheck_enabled("engine") is True
    assert main._startup_data_selfcheck_enabled("worker") is False
    assert main._startup_data_selfcheck_enabled("frontdoor") is False


def test_frontdoor_uses_reviewed_decomposed_pool_cap(monkeypatch) -> None:
    from db import session as db_session

    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project")
    monkeypatch.setenv("RUN_MODE", "frontdoor")
    monkeypatch.setenv("DB_ROLE", "frontdoor")
    monkeypatch.setenv("PUBLIC_TESTING_MODE", "0")
    monkeypatch.setenv("DB_USE_NULLPOOL", "0")
    monkeypatch.setenv("DB_POOL_SIZE", "5")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    monkeypatch.setenv("DB_POOL_RAILWAY_ABSOLUTE_CAP", "5")
    monkeypatch.setenv("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP", "1")
    monkeypatch.setenv("DB_ALLOW_REVIEWED_MONOLITH_POOL", "0")

    assert db_session._effective_pool_settings() == (5, 1)


def test_railway_entrypoint_and_split_script_cannot_silently_restore_monolith() -> None:
    start = Path("start.sh").read_text(encoding="utf-8")
    railway = Path("railway_main.py").read_text(encoding="utf-8")
    split = Path("split_signalrank_railway.ps1").read_text(encoding="utf-8")

    assert '_start_frontdoor()' in start
    assert 'export RUN_ENGINE_LOOP="0"' in start
    assert 'export RUN_WORKER_LOOP="0"' in start
    assert "refusing hidden monolith fallback" in start

    assert "[runtime_ownership]" in railway
    assert "Engine loop skipped by ownership" in railway
    assert "Worker loop skipped by ownership" in railway

    assert 'RUN_MODE = "frontdoor"' in split
    assert 'DB_ROLE = "frontdoor"' in split
    assert 'DB_ROLE = "engine"' in split
    assert 'DB_ROLE = "worker"' in split
    assert 'DB_POOL_RAILWAY_ABSOLUTE_CAP = "5"' in split
    assert 'STARTUP_OPS_ENABLED = "0"' in split
