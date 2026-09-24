from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.signal_lifecycle import ACTIVE_TRADE
from engine.realtime_outcome_tracker import _database_tp_progress, _get_tp_progress


def test_database_progress_reads_explicit_lifecycle_highest_tp():
    lifecycle = SimpleNamespace(
        state=ACTIVE_TRADE,
        highest_tp_hit=2,
        tp1_hit_at=None,
        tp2_hit_at=None,
        tp3_hit_at=None,
    )
    outcome = SimpleNamespace(status="pending", meta={})
    assert _database_tp_progress(lifecycle, outcome) == 2


@pytest.mark.asyncio
async def test_tp_progress_uses_redis_projection_while_db_projection_catches_up(monkeypatch):
    async def cache_get(_key):
        return "2"

    monkeypatch.setattr("core.redis_state.state.cache_get", cache_get)
    signal = {
        "signal_id": "sig-1",
        "highest_tp_hit": 0,
        "lifecycle_state": ACTIVE_TRADE,
        "prev_outcome_status": "pending",
        "prev_outcome_meta": {},
    }
    assert await _get_tp_progress(signal) == 2


def test_duplicate_lifecycle_event_has_projection_repair_path():
    from pathlib import Path
    source = Path("engine/signal_lifecycle.py").read_text(encoding="utf-8")
    block = source[source.index("if existing is not None:"):source.index("if existing is None:", source.index("if existing is not None:"))]
    assert "Self-heal legacy/partially committed lifecycle rows" in block
    assert "lifecycle.highest_tp_hit = tp_stage" in block
    assert "lifecycle.state = recorded_state" in block
    assert "current_state not in TERMINAL_STATES" in block
