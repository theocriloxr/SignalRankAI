from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_engine_round_robin_is_class_interleaved_and_persistent() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    queue = (ROOT / "engine" / "cycle_queue.py").read_text(encoding="utf-8")

    assert "AssetCycleQueue" in source
    assert "_cycle_queue = AssetCycleQueue()" in source
    assert "_cat_iters = [iter(c) for c in [crypto_assets, fx_assets, stock_assets, index_assets, commodity_assets] if c]" in source
    assert "_cycle_queue.refresh_universe(_all_open, force=(cycle_no == 1))" in source
    assert "_cycle_queue.pop_batch(CYCLE_BATCH_SIZE)" in source
    assert "every asset in the current round has been" in queue
    assert "self._queue = deque(self._universe)" in queue


def test_every_open_asset_class_gets_rotating_cycle_coverage_when_capacity_allows() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    block = source[
        source.index("# Guarantee class coverage:"):
        source.index("cycle_assets = len(assets)")
    ]

    for name in ("crypto", "fx", "stock", "index", "commodity"):
        assert f'"{name}"' in block
    assert "_required_classes = [k for k, v in _open_by_class.items() if v]" in block
    assert "CYCLE_BATCH_SIZE < len(_required_classes)" in block
    assert "_class_cursor.get(_cls, 0) % len(_pool)" in block
    assert "_selected_counts.get(_existing_cls, 0) > 1" in block
    assert "_cycle_queue.remove_from_queue(_injected)" in block


def test_closed_or_disabled_classes_do_not_consume_fairness_slots() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    disabled_filter = source.index("_filter_assets_by_enabled_classes(open_assets)")
    partitions = source.index("crypto_assets = [a for a in open_assets if is_crypto(a)]")
    fairness = source.index("# Guarantee class coverage:")
    assert disabled_filter < partitions < fairness
