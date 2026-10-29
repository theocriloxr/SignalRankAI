"""Every database call made from the engine loop is bounded (follow-up to the 22 Oct stall).

The production loop froze when a write on a connection killed by a Postgres
restart never returned. The stall watchdog restarts a stuck engine; these tests
make sure the loop does not get stuck on its own database calls in the first place.
"""
from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

import engine.core as engine_core

ROOT = Path(__file__).resolve().parents[1]
# Only reached when utils.async_runner (which supports timeouts) failed to import.
ALLOWED_UNBOUNDED = {"cfg = run_sync(refresh_fn(force=force))"}


def test_no_run_sync_call_in_the_engine_loop_can_wait_forever():
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    unbounded = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in {"run_sync", "_run_sync"}:
            continue
        if "timeout" in {k.arg for k in node.keywords} or len(node.args) >= 2:
            continue
        line = source.splitlines()[node.lineno - 1].strip()
        if line not in ALLOWED_UNBOUNDED:
            unbounded.append(f"engine/core.py:{node.lineno}: {line}")
    assert not unbounded, unbounded


def test_timeout_setting_is_bounded(monkeypatch):
    monkeypatch.delenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", raising=False)
    assert engine_core._db_call_timeout() == 10.0
    monkeypatch.setenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", "0")
    assert engine_core._db_call_timeout() == 1.0
    monkeypatch.setenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", "9999")
    assert engine_core._db_call_timeout() == 120.0
    monkeypatch.setenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", "nan")
    assert engine_core._db_call_timeout() == 10.0
    monkeypatch.setenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", "junk")
    assert engine_core._db_call_timeout() == 10.0


def test_a_decision_write_that_never_returns_does_not_stall_the_loop(monkeypatch):
    async def never_returns(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setenv("ENGINE_DB_CALL_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr(engine_core, "persist_decision_log", never_returns)
    monkeypatch.setattr(engine_core._ml_rejection_tracker, "persist_rejection", never_returns)
    signal = {"signal_id": "s1", "asset": "BTCUSDT", "timeframe": "1h", "direction": "LONG",
              "entry": 100.0, "stop_loss": 98.0, "take_profit": [104.0]}
    started = time.monotonic()
    engine_core._log_decision("rejected", signal, reason="test")
    assert time.monotonic() - started < 6.0  # two bounded writes, never forever


def test_run_sync_honours_timeout_when_background_threads_are_disabled(monkeypatch):
    import pytest

    from utils import async_runner

    async def never_returns():
        await asyncio.Event().wait()

    monkeypatch.setattr(async_runner, "_background_workers_disabled", lambda: True)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        async_runner.run_sync(never_returns(), timeout=0.5)
    assert time.monotonic() - started < 3.0
