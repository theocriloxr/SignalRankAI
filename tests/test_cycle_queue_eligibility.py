"""Runtime removals take effect between scheduled discovery refreshes."""
from engine.cycle_queue import AssetCycleQueue


def test_disabled_members_never_survive_pending_or_refilled_batches(monkeypatch):
    monkeypatch.setattr("engine.cycle_queue.time.monotonic", lambda: 100.0)
    queue = AssetCycleQueue()
    queue.refresh_universe(["BTCUSDT", "EURUSD", "AAPL"], force=True)
    assert queue.pop_batch(1) == ["BTCUSDT"]
    queue.mark_done(["BTCUSDT"])
    queue.refresh_universe(["BTCUSDT", "ETHUSDT"])
    assert queue.universe_size == 1
    assert queue.queue_remaining == 0
    assert queue.pop_batch(10) == ["BTCUSDT"]
    queue.refresh_universe([])
    assert queue.pop_batch(10) == []
    assert queue.universe_size == 0


def test_additions_wait_for_refresh_and_preserve_existing_round_order(monkeypatch):
    instant = [100.0]
    monkeypatch.setattr("engine.cycle_queue.time.monotonic", lambda: instant[0])
    queue = AssetCycleQueue()
    queue.refresh_universe(["BTCUSDT", "ETHUSDT", "AAPL"], force=True)
    queue.mark_done(queue.pop_batch(1))
    queue.refresh_universe(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    assert queue.pop_batch(10) == ["ETHUSDT"]
    queue.mark_done(["ETHUSDT"])
    instant[0] += 3601
    queue.refresh_universe(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    assert queue.pop_batch(10) == ["SOLUSDT"]
    queue.mark_done(["SOLUSDT"])
    assert queue.pop_batch(10) == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
