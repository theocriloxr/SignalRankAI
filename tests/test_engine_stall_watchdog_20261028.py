"""Production engine stalled for six days while Railway reported it Online.

Read-only logs (28 Oct 2026): last pipeline step 2026-10-22 08:08:30 UTC, then
the database restarted and the loop never logged again. The watchdog must name
the stuck call, publish a not-ready ``stalled`` heartbeat, exit a dedicated
engine process so it restarts, and never kill a process that serves HTTP.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from engine import stall_watchdog as wd

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setenv("ENGINE_STALL_SECONDS", "120")
    wd.mark("test")
    yield


def _age(seconds: float) -> None:
    with wd._lock:
        wd._state["at"] = time.monotonic() - seconds


def test_no_report_while_the_loop_progresses():
    published, exits = [], []
    assert wd.check(published.append, exits.append) is False
    assert published == [] and exits == []


def test_stall_alerts_with_stage_and_does_not_exit_a_shared_process(monkeypatch):
    monkeypatch.setenv("ENGINE_STALL_ACTION", "alert")
    wd.mark("pipeline:PENGUUSDT")
    _age(500)
    published, exits = [], []
    assert wd.check(published.append, exits.append) is True
    assert published[0]["status"] == "stalled" and published[0]["stall_stage"] == "pipeline:PENGUUSDT"
    assert published[0]["stall_age_seconds"] >= 500
    assert exits == []


def test_stall_exits_a_dedicated_engine_with_code_70(monkeypatch):
    monkeypatch.setenv("ENGINE_STALL_ACTION", "exit")
    _age(500)
    exits = []
    wd.check(None, exits.append)
    assert exits == [wd.EXIT_CODE] == [70]


def test_default_action_depends_on_the_process_role(monkeypatch):
    monkeypatch.delenv("ENGINE_STALL_ACTION", raising=False)
    monkeypatch.setitem(sys.modules, "railway_main", object())
    assert wd.stall_action() == "alert"
    monkeypatch.delitem(sys.modules, "railway_main")
    monkeypatch.setenv("RUN_MODE", "engine")
    assert wd.stall_action() == "exit"
    monkeypatch.setenv("RUN_MODE", "web")
    assert wd.stall_action() == "alert"


def test_the_stack_of_the_stuck_thread_names_the_blocking_call():
    gate, ready = threading.Event(), threading.Event()

    def blocked_in_database_call():
        wd.mark("pipeline:BTCUSDT")
        ready.set()
        gate.wait(5)

    worker = threading.Thread(target=blocked_in_database_call, daemon=True)
    worker.start()
    ready.wait(5)
    try:
        assert "blocked_in_database_call" in wd.thread_stack(wd.snapshot()["thread_id"])
    finally:
        gate.set()
        worker.join(5)


def test_stalled_heartbeat_does_not_count_as_progress(monkeypatch):
    import engine.core as engine_core

    monkeypatch.setattr(engine_core.state, "set_sync", lambda *a, **k: None)
    wd.mark("before")
    _age(300)
    engine_core._publish_engine_stall({"status": "stalled", "stall_stage": "before", "stall_age_seconds": 300})
    assert wd.snapshot()["age_seconds"] >= 300
    engine_core._publish_engine_cycle_state({"status": "started"})
    assert wd.snapshot()["age_seconds"] < 5 and wd.snapshot()["stage"] == "started"


def test_engine_starts_the_watchdog_and_readiness_names_a_stall():
    core = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    loop = core[core.index("def main_loop("):]
    assert loop.index("stall_watchdog.start(publish=_publish_engine_stall)") < loop.index("    while True:")
    assert 'stall_watchdog.mark(f"pipeline:{asset}")' in loop
    probe = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    block = probe[probe.index('raw_cycle = state.get_sync("engine:last_cycle")'):]
    healthy = block[block.index("status_ok = "): block.index('checks["engine_runtime"] = {')]
    assert '"stalled"' not in healthy and 'cycle.get("status") == "stalled"' in block
