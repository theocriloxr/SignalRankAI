"""Class coverage without discarding assets already popped for this cycle."""
from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence

from engine.cycle_queue import AssetCycleQueue


def schedule_cycle(
    queue: AssetCycleQueue, universe: Sequence[str], *,
    capacity: int, force_refresh: bool, pools: Mapping[str, Sequence[str]],
    cursors: MutableMapping[str, int], classify: Callable[[str], str],
) -> tuple[list[str], dict[str, int]]:
    """Keep the entire eligible queue while bounding each cycle's work."""
    if capacity < 1:
        raise ValueError("invalid_cycle_capacity")
    queue.refresh_universe(list(universe), force=force_refresh)
    return cover_open_classes(queue, queue.pop_batch(capacity), pools=pools,
                              cursors=cursors, classify=classify, capacity=capacity)


def cover_open_classes(
    queue: AssetCycleQueue, batch: Sequence[str], *,
    pools: Mapping[str, Sequence[str]], cursors: MutableMapping[str, int],
    classify: Callable[[str], str], capacity: int,
) -> tuple[list[str], dict[str, int]]:
    """Rotate class anchors and return every displaced asset to pending work.

    Anchors may repeat to cover small classes, but an unprocessed member is
    never acknowledged or silently dropped to make room for an anchor.
    """
    selected = list(batch)
    if capacity < 1 or len(selected) > capacity or len(set(selected)) != len(selected):
        raise ValueError("invalid_cycle_batch")
    counts = {key: 0 for key in pools}
    for asset in selected:
        key = classify(asset)
        counts[key] = counts.get(key, 0) + 1
    injected: list[str] = []
    displaced: set[str] = set()
    for key, pool in pools.items():
        if not pool or counts.get(key, 0):
            continue
        candidate = None
        for _ in range(len(pool)):
            index = cursors.get(key, 0) % len(pool)
            cursors[key] = cursors.get(key, 0) + 1
            if pool[index] not in selected:
                candidate = pool[index]
                break
        if candidate is None:
            continue
        if len(selected) < capacity:
            selected.append(candidate)
        else:
            replacement = next((i for i in range(len(selected) - 1, -1, -1)
                                if counts.get(classify(selected[i]), 0) > 1), None)
            if replacement is None:
                continue
            removed = selected[replacement]
            counts[classify(removed)] -= 1
            displaced.add(removed)
            selected[replacement] = candidate
        counts[key] = counts.get(key, 0) + 1
        injected.append(candidate)
    queue.remove_from_queue(injected)
    queue.return_to_front([asset for asset in batch if asset in displaced])
    return selected, counts
