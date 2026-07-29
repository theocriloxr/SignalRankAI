from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _function_source(name: str) -> str:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def test_database_readiness_uses_bounded_railway_safe_timeout() -> None:
    helper = _function_source("_database_readiness_timeout_seconds")
    assert 'DB_READINESS_TIMEOUT_SECONDS' in helper
    assert 'or "8"' in helper
    assert 'max(2.0, min(30.0, value))' in helper


def test_database_readiness_uses_critical_lane_and_one_round_trip() -> None:
    source = _function_source("_database_readiness_check")
    tree = ast.parse(source)
    execute_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    ]
    assert len(execute_calls) == 1
    assert 'priority=DBPriority.CRITICAL' in source
    assert 'timeout_seconds=timeout_s' in source
    assert 'timeout=timeout_s' in source
    assert 'timeout_seconds=1.5' not in source
    assert 'text("SELECT 1")' not in source
    assert 'active_guard_present' in source
    assert 'signals_performance_version' in source


def test_railway_profiles_publish_readiness_timeout() -> None:
    profiles = sorted((ROOT / "configs" / "env").glob("railway-*.env.example"))
    assert profiles
    for profile in profiles:
        text = profile.read_text(encoding="utf-8")
        assert 'DB_READINESS_TIMEOUT_SECONDS=8' in text, profile.name


def test_release_version_is_current() -> None:
    text = (ROOT / "core" / "version.py").read_text(encoding="utf-8")
    assert 'default="1.2.0"' in text

import contextlib
import pytest


@pytest.mark.asyncio
async def test_database_readiness_returns_ready_from_consolidated_row(monkeypatch) -> None:
    import db.session as db_session
    import railway_main

    captured: dict[str, object] = {}

    class _Mappings:
        def one(self):
            return {
                "deployed_revision": "0023_signal_runtime_schema",
                "decision_log_created_at": True,
                "signals_mfe_pct": True,
                "signals_mae_pct": True,
                "signals_performance_version": True,
                "active_guard_present": True,
            }

    class _Result:
        def mappings(self):
            return _Mappings()

    class _Session:
        async def execute(self, statement):
            captured["statement"] = str(statement)
            return _Result()

        async def rollback(self):
            captured["rolled_back"] = True

    @contextlib.asynccontextmanager
    async def _get_session(**kwargs):
        captured["kwargs"] = kwargs
        yield _Session()

    monkeypatch.setattr(db_session, "is_db_configured", lambda: True)
    monkeypatch.setattr(db_session, "get_session", _get_session)
    monkeypatch.setenv("DB_READINESS_TIMEOUT_SECONDS", "8")

    result = await railway_main._database_readiness_check()

    assert result["ok"] is True
    assert result["revision"] == "0023_signal_runtime_schema"
    assert result["probe_timeout_seconds"] == 8.0
    assert captured["rolled_back"] is True
    assert captured["kwargs"]["label"] == "readiness"
    assert captured["kwargs"]["timeout_seconds"] == 8.0
    assert "signals_performance_version" in captured["statement"]
