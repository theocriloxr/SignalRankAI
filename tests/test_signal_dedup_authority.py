"""Unavailable durable history must never authorize another trade thesis."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from engine import signal_deduplicator as module
from engine import signal_dedup_strict as strict_module


def install_history(monkeypatch, *, rows=(), failure=None):
    class Session:
        async def execute(self, statement):
            if failure == "query":
                raise RuntimeError("database-password-must-not-be-logged")
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    @asynccontextmanager
    async def scope():
        if failure == "admission":
            raise TimeoutError("database-password-must-not-be-logged")
        yield Session()
        if failure == "exit":
            raise RuntimeError("database-password-must-not-be-logged")

    monkeypatch.setattr(module, "get_session", scope)
    monkeypatch.setattr(strict_module, "get_session", scope)


@pytest.mark.parametrize("failure", ["admission", "query", "exit"])
def test_history_failure_blocks_candidate_and_cannot_look_like_empty_history(monkeypatch, caplog, failure):
    install_history(monkeypatch, failure=failure)
    dedup = module.SignalDeduplicator()
    assert asyncio.run(dedup.is_duplicate("BTCUSDT", "1h", "long", 100))
    with pytest.raises(module.DedupAuthorityUnavailable):
        asyncio.run(dedup.get_recent_signals("BTCUSDT", "1h", "long"))
    with pytest.raises(module.DedupAuthorityUnavailable):
        asyncio.run(dedup.find_semantic_duplicates({"asset": "BTCUSDT", "timeframe": "1h", "direction": "long", "entry": 100}))
    assert "database-password-must-not-be-logged" not in caplog.text


@pytest.mark.parametrize("failure", ["admission", "query", "exit"])
def test_strict_history_failure_also_blocks_and_redacts(monkeypatch, caplog, failure):
    install_history(monkeypatch, failure=failure)
    dedup = strict_module.StrictSignalDedup()
    assert asyncio.run(dedup.is_duplicate_strict("BTCUSDT", "1h", "BUY")) == (True, None)
    with pytest.raises(module.DedupAuthorityUnavailable):
        asyncio.run(dedup.find_duplicates_strict("BTCUSDT", "1h", "BUY"))
    assert "database-password-must-not-be-logged" not in caplog.text


def test_strict_verified_empty_history_is_distinct_from_failure(monkeypatch):
    install_history(monkeypatch)
    dedup = strict_module.StrictSignalDedup()
    assert asyncio.run(dedup.is_duplicate_strict("BTCUSDT", "1h", "BUY")) == (False, None)
    assert asyncio.run(dedup.is_duplicate_strict("BTCUSDT", "1h", "invalid")) == (True, None)
    assert asyncio.run(dedup.find_duplicates_strict("BTCUSDT", "1h", "BUY")) == []


def test_strict_batch_clusters_side_aliases_and_keeps_best_score():
    signals = [{"asset": "BTCUSDT", "timeframe": "1h", "direction": side, "score": score} for side, score in [("long", 80), ("BUY", 90)]]
    dedup = strict_module.StrictSignalDedup()
    assert asyncio.run(dedup.dedupe_batch_strict(signals)) == [signals[1]]
    assert dedup._make_key("BTCUSDT", "1h", "BUY") == dedup._make_key("BTCUSDT", "1h", "long")


@pytest.mark.parametrize("entry", [0, -1, float("nan"), float("inf"), float("-inf"), "invalid"])
def test_invalid_entry_cannot_receive_dedup_clearance(monkeypatch, entry):
    install_history(monkeypatch)
    assert asyncio.run(module.SignalDeduplicator().is_duplicate("BTCUSDT", "1h", "long", entry))


def test_verified_empty_database_history_allows_valid_candidate(monkeypatch):
    install_history(monkeypatch)
    dedup = module.SignalDeduplicator()
    assert not asyncio.run(dedup.is_duplicate("BTCUSDT", "1h", "long", 100))
    assert asyncio.run(dedup.get_recent_signals("BTCUSDT", "1h", "long")) == []


@pytest.mark.parametrize("direction", ["long", "BUY", "buy"])
@pytest.mark.parametrize("stored_direction", ["long", "BUY"])
def test_side_aliases_cannot_bypass_recent_matching_thesis(monkeypatch, direction, stored_direction):
    row = SimpleNamespace(asset="BTCUSDT", timeframe="1h", direction=stored_direction, entry=100,
                          stop_loss=99, take_profit=102, created_at=datetime.utcnow(), signal_id="recent")
    install_history(monkeypatch, rows=[row])
    assert asyncio.run(module.SignalDeduplicator().is_duplicate("BTCUSDT", "1h", direction, 100))


@pytest.mark.parametrize("signal", [{"timeframe": "1h", "direction": "long"}, {"asset": "BTCUSDT", "timeframe": "1h", "direction": "sideways"}])
def test_invalid_semantic_scope_cannot_look_like_verified_empty_history(monkeypatch, signal):
    install_history(monkeypatch)
    with pytest.raises(module.DedupAuthorityUnavailable):
        asyncio.run(module.SignalDeduplicator().find_semantic_duplicates(signal))


def test_capped_history_cannot_prove_absence(monkeypatch):
    row = SimpleNamespace(asset="ETHUSDT", timeframe="1h", direction="long", entry=100,
                          stop_loss=99, take_profit=102, created_at=datetime.utcnow(), signal_id="other")
    install_history(monkeypatch, rows=[row] * 250)
    dedup = module.SignalDeduplicator()
    assert asyncio.run(dedup.is_duplicate("BTCUSDT", "1h", "long", 100))
    with pytest.raises(module.DedupAuthorityUnavailable):
        asyncio.run(dedup.get_recent_signals("BTCUSDT", "1h", "long"))


def test_sparse_rejection_cycle_returns_zero(monkeypatch):
    class Session:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        async def execute(self, statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    @asynccontextmanager
    async def scope():
        yield Session()
    async def flush(**kwargs):
        return 0
    tracker = module.MLRejectionTracker()
    monkeypatch.setattr(module, "get_session", scope)
    monkeypatch.setattr(tracker, "flush_pending_rejections", flush)
    assert asyncio.run(tracker.track_rejection_outcomes()) == 0
