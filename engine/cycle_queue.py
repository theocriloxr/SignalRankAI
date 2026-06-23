"""engine/cycle_queue.py — Round-robin asset scanner queue.

Guarantees every discovered (and manually-configured) asset is processed
exactly once per round before any asset is repeated. A new round begins
automatically when the queue drains.

Designed for the engine main_loop::

    queue = AssetCycleQueue()                    # once, before the while-loop

    # Each wakeup:
    queue.refresh_universe(open_assets,
                           force=first_wakeup)
    batch = queue.pop_batch(CYCLE_BATCH_SIZE)    # process these assets
    ... run pipeline on batch ...
    queue.mark_done(batch, signals_generated=N)

Environment variables
---------------------
CYCLE_BATCH_SIZE
    Number of assets to process per engine wakeup (default 10).
CYCLE_UNIVERSE_REFRESH_INTERVAL
    Seconds between full universe rebuilds from pair-discovery (default 3600).
"""
from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from collections import deque
from typing import Deque, List

logger = logging.getLogger(__name__)


class AssetCycleQueue:
    """Thread-safe round-robin queue over assets.

    Lifecycle
    ---------
    * ``refresh_universe(assets)`` — update the canonical asset universe;
      newly-discovered assets are appended to the *tail* of the current queue
      so they are included in this round without discarding already-queued
      work. Runs at most once per ``CYCLE_UNIVERSE_REFRESH_INTERVAL`` seconds
      unless *force=True*.

    * ``pop_batch(n)`` — pop up to *n* assets for processing; triggers a new
      round automatically when the queue drains.

    * ``mark_done(assets, signals_generated)`` — acknowledge processed assets
      and accumulate per-round stats.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: Deque[str] = deque()
        self._done_this_round: set[str] = set()
        self._universe: list[str] = []
        self._round_no: int = 0
        self._last_refresh: float = 0.0

        self._refresh_interval: float = self._read_refresh_interval_seconds()

        # Round-level stats
        self._round_signals: int = 0
        self._round_assets_done: int = 0

    # ─────────────────────────── public API ───────────────────────────

    def refresh_universe(self, assets: List[str], *, force: bool = False) -> None:
        """Merge *assets* into the canonical universe.

        New assets not yet seen this round are appended to the queue tail.
        Already-queued and already-done assets are left untouched. The rebuild
        only fires once per ``_refresh_interval`` unless *force=True*.
        """
        now = time.monotonic()
        try:
            with self._lock:
                if not force and (now - self._last_refresh) < self._refresh_interval:
                    return
                self._last_refresh = now

                ordered = self._normalize_assets(assets)

                # Append assets brand-new to this round.
                existing = set(self._queue) | self._done_this_round
                added = 0
                for asset in ordered:
                    if asset not in existing:
                        self._queue.append(asset)
                        existing.add(asset)
                        added += 1

                self._universe = ordered
                logger.info(
                    "[cycle_queue] universe updated: %d assets total, "
                    "+%d new appended, queue_remaining=%d, round=%d",
                    len(ordered), added, len(self._queue), self._round_no,
                )
        except Exception:
            logger.error("[cycle_queue] refresh_universe failed: %s", traceback.format_exc())

    def pop_batch(self, size: int = 10) -> List[str]:
        """Pop up to *size* assets from the queue.

        If the queue is empty (every asset in the current round has been
        processed), a new round starts automatically and the queue is refilled
        from the last universe snapshot before popping.
        """
        with self._lock:
            if not self._queue:
                self._start_new_round()

            safe_size = self._normalize_batch_size(size)
            batch: List[str] = []
            for _ in range(safe_size):
                if not self._queue:
                    break
                batch.append(self._queue.popleft())
            return batch

    def mark_done(self, assets: List[str], signals_generated: int = 0) -> None:
        """Record *assets* as processed this round and accumulate stats."""
        with self._lock:
            normalized = self._normalize_assets(assets)

            newly_done = 0
            for asset in normalized:
                if asset not in self._done_this_round:
                    self._done_this_round.add(asset)
                    newly_done += 1

            self._round_assets_done += newly_done
            self._round_signals += max(0, int(signals_generated))

    def remove_from_queue(self, assets: List[str]) -> int:
        """Remove specific assets from the pending queue tail/head.

        Returns number of removed assets.
        Useful when caller force-injects class coverage assets into the
        current cycle batch and wants to avoid duplicates later in round.
        """
        with self._lock:
            targets = set(self._normalize_assets(assets))
            if not targets:
                return 0
            before = len(self._queue)
            self._queue = deque([asset for asset in self._queue if asset not in targets])
            return max(0, before - len(self._queue))

    # ─────────────────────────── properties ───────────────────────────

    @property
    def round_no(self) -> int:
        return self._round_no

    @property
    def queue_remaining(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def universe_size(self) -> int:
        with self._lock:
            return len(self._universe)

    @property
    def pending_assets_snapshot(self) -> List[str]:
        """Snapshot of currently queued assets, preserving queue order."""
        with self._lock:
            return list(self._queue)

    @property
    def round_progress(self) -> str:
        """Human-readable one-liner for log output."""
        with self._lock:
            total = len(self._universe)
            done = len(self._done_this_round)
            return (
                f"round={self._round_no} "
                f"progress={done}/{total} "
                f"queue_left={len(self._queue)}"
            )

    # ─────────────────────────── internals ────────────────────────────

    def _start_new_round(self) -> None:
        """Called with ``_lock`` held when the queue has drained."""
        prev_done = len(self._done_this_round)
        prev_sigs = self._round_signals
        self._round_no += 1
        self._done_this_round.clear()
        self._round_signals = 0
        self._round_assets_done = 0
        self._queue = deque(self._universe)
        logger.info(
            "[cycle_queue] ══ Round %d started ══ %d assets queued "
            "(prev round: %d assets processed, %d signals generated)",
            self._round_no, len(self._queue), prev_done, prev_sigs,
        )

    @staticmethod
    def _normalize_assets(assets: List[str] | None) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw in (assets or []):
            asset = str(raw or "").strip()
            if asset and asset not in seen:
                ordered.append(asset)
                seen.add(asset)
        return ordered

    @staticmethod
    def _normalize_batch_size(size: int) -> int:
        try:
            normalized = int(size)
        except Exception:
            normalized = 10
        return max(1, normalized)

    @staticmethod
    def _read_refresh_interval_seconds() -> float:
        raw = os.getenv("CYCLE_UNIVERSE_REFRESH_INTERVAL", "3600")
        try:
            parsed = float(str(raw).strip() or "3600")
        except Exception:
            logger.warning(
                "[cycle_queue] invalid CYCLE_UNIVERSE_REFRESH_INTERVAL=%r; defaulting to 3600",
                raw,
            )
            return 3600.0
        if parsed <= 0:
            logger.warning(
                "[cycle_queue] non-positive CYCLE_UNIVERSE_REFRESH_INTERVAL=%s; defaulting to 3600",
                parsed,
            )
            return 3600.0
        return parsed
