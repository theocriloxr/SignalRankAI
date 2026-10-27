"""Production /readyz reports `engine_heartbeat_missing` (24 Oct 2026).

The engine wrote `engine:last_cycle` only after universe selection, so every
early exit (circuit breaker active or failing closed, no assets, off-market
throttle, empty queue) left no trace: a live engine skipping every cycle looked
exactly like a stopped one. Skips now publish a `skipped` heartbeat with the
reason. `skipped` must never satisfy readiness.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import engine.core as engine_core

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
RAILWAY = (ROOT / "railway_main.py").read_text(encoding="utf-8")


def test_skip_heartbeat_payload_names_reason_and_identity(monkeypatch):
    written = {}

    def fake_set_sync(key, value, ex=None):
        written.update(key=key, value=json.loads(value), ex=ex)

    monkeypatch.setattr(engine_core.state, "set_sync", fake_set_sync)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deploy-1")

    engine_core._publish_engine_cycle_skip(7, "circuit_breaker_check_failed:TimeoutError", 30)

    assert written["key"] == "engine:last_cycle"
    payload = written["value"]
    assert payload["status"] == "skipped"
    assert payload["skip_reason"] == "circuit_breaker_check_failed:TimeoutError"
    assert payload["cycle"] == 7
    assert payload["git_sha"] == "a" * 40
    assert payload["deployment_id"] == "deploy-1"
    assert payload["next_attempt_in_seconds"] == 30
    assert payload["started_at"].endswith("+00:00")
    assert written["ex"] >= 60


def test_skip_heartbeat_never_raises_when_redis_fails(monkeypatch):
    def broken(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(engine_core.state, "set_sync", broken)
    engine_core._publish_engine_cycle_skip(1, "no_assets", 5)


def test_every_early_cycle_exit_publishes_a_skip_before_continuing():
    loop = ENGINE[ENGINE.index("def main_loop("):]
    loop = loop[loop.index("    while True:"):]
    before_selection = loop[: loop.index("_publish_engine_cycle_state(_cycle_state)")]
    exits = [m.start() for m in re.finditer(r"^\s+continue$", before_selection, flags=re.M)]
    assert len(exits) >= 5
    for position in exits:
        preceding = before_selection[max(0, position - 400): position]
        assert "_publish_engine_cycle_skip(" in preceding, before_selection[position - 400: position + 20]


def test_skipped_is_not_a_ready_engine_status_and_reason_is_surfaced():
    start = RAILWAY.index('raw_cycle = state.get_sync("engine:last_cycle")')
    probe = RAILWAY[start: RAILWAY.index("# Admin pulse stays visible", start)]
    healthy = probe[probe.index("status_ok = "): probe.index("checks[\"engine_runtime\"] = {")]
    assert '"skipped"' not in healthy
    assert 'cycle.get("status") == "skipped"' in probe
    assert '["skip_reason"]' in probe
