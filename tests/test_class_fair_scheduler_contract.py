"""Exercise the engine scheduler, including coverage displacement and caps."""
from engine.cycle_queue import AssetCycleQueue
from engine.cycle_selection import schedule_cycle


def run_cycle(queue, universe, pools, cursors, *, capacity, first=False):
    classes = {asset: key for key, members in pools.items() for asset in members}
    batch, counts = schedule_cycle(queue, universe, capacity=capacity, force_refresh=first,
                                  pools=pools, cursors=cursors, classify=classes.__getitem__)
    queue.mark_done(batch)
    return batch, counts


def test_small_work_cap_never_permanently_excludes_the_universe_tail():
    queue = AssetCycleQueue()
    pools = {"crypto": [f"C{i}USDT" for i in range(41)], "fx": ["EURUSD"],
             "stock": ["AAPL"], "index": ["NAS100"], "commodity": ["XAUUSD"]}
    universe = [asset for pool in pools.values() for asset in pool]
    cursors = {}
    seen = set()
    for cycle in range(41):
        batch, counts = run_cycle(queue, universe, pools, cursors, capacity=5, first=cycle == 0)
        assert len(batch) <= 5 and len(batch) == len(set(batch))
        assert all(counts[key] >= 1 for key in pools)
        assert queue.universe_size == len(universe)
        seen.update(batch)
    assert seen == set(universe)
    assert queue.queue_remaining == 0
    assert queue.round_no == 0


def test_anchors_rotate_without_losing_displaced_tail_members():
    queue = AssetCycleQueue()
    pools = {"crypto": [f"C{i}USDT" for i in range(10)], "fx": ["EURUSD", "GBPUSD"]}
    universe = pools["crypto"] + pools["fx"]
    cursors = {}
    batches = [run_cycle(queue, universe, pools, cursors, capacity=2, first=True)[0]]
    for _ in range(9):
        batches.append(run_cycle(queue, universe, pools, cursors, capacity=2)[0])
    assert [batch[0] for batch in batches] == pools["crypto"]
    assert [batch[1] for batch in batches] == ["EURUSD", "GBPUSD"] * 5
    assert queue.queue_remaining == 0


def test_closed_or_disabled_classes_cannot_be_requeued_or_consume_slots():
    queue = AssetCycleQueue()
    pools = {"crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "fx": ["EURUSD"]}
    universe = pools["crypto"] + pools["fx"]
    first, _ = run_cycle(queue, universe, pools, {}, capacity=2, first=True)
    assert first == ["BTCUSDT", "EURUSD"]
    pools = {"crypto": ["BTCUSDT", "SOLUSDT"]}
    queue.refresh_universe(pools["crypto"])
    queue.return_to_front(["ETHUSDT", "EURUSD", "BTCUSDT", "SOLUSDT", "SOLUSDT"])
    batch, counts = run_cycle(queue, pools["crypto"], pools, {}, capacity=2)
    assert batch == ["SOLUSDT"]
    assert counts == {"crypto": 1}
    assert queue.queue_remaining == 0


def test_capacity_smaller_than_class_count_preserves_progress_and_budget():
    queue = AssetCycleQueue()
    pools = {"crypto": ["BTCUSDT", "ETHUSDT"], "fx": ["EURUSD"], "stock": ["AAPL"]}
    universe = [asset for pool in pools.values() for asset in pool]
    seen = []
    for cycle in range(len(universe)):
        batch, _ = run_cycle(queue, universe, pools, {}, capacity=1, first=cycle == 0)
        assert len(batch) == 1
        seen.extend(batch)
    assert seen == universe


def test_single_class_completes_each_round_before_repeating():
    queue = AssetCycleQueue()
    pools = {"crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT", "XRPUSDT"]}
    seen = []
    for cycle in range(3):
        batch, _ = run_cycle(queue, pools["crypto"], pools, {}, capacity=2, first=cycle == 0)
        seen.extend(batch)
    assert seen == pools["crypto"]
    assert run_cycle(queue, pools["crypto"], pools, {}, capacity=2)[0] == pools["crypto"][:2]
