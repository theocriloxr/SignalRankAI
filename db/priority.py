from __future__ import annotations

import threading
from collections import deque
import time
from enum import Enum
from typing import Any


class DBPriority(str, Enum):
    """Database work classes ordered by user and delivery impact."""

    INTERACTIVE = "interactive"
    CRITICAL = "critical"
    BACKGROUND = "background"
    ANALYTICS = "analytics"


class DBAdmissionController:
    """Small, synchronous admission controller for a shared DB pool.

    Interactive and critical work each receive a dedicated foreground lane.
    Background and analytics work may borrow capacity only while no foreground
    request is waiting. Borrowers never consume every slot, which keeps a
    foreground lane available even with a two-connection pool.
    """

    def __init__(
        self,
        capacity: int,
        *,
        background_limit: int | None = None,
        interactive_limit: int | None = None,
        critical_limit: int | None = None,
        analytics_limit: int | None = None,
        analytics_enabled: bool = True,
        foreground_reserve: int | None = None,
    ) -> None:
        self.capacity = max(1, int(capacity))
        self.analytics_enabled = bool(analytics_enabled)
        default_reserve = 1 if self.capacity <= 2 else min(4, max(2, self.capacity // 4))
        requested_reserve = default_reserve if foreground_reserve is None else int(foreground_reserve)
        self.foreground_reserve = max(1, min(self.capacity, requested_reserve))
        borrower_capacity = max(1, self.capacity - self.foreground_reserve)
        default_interactive = 1 if self.capacity <= 2 else max(1, self.foreground_reserve // 2)
        default_critical = 1 if self.capacity <= 2 else max(1, self.foreground_reserve - default_interactive)
        self.limits = {
            DBPriority.INTERACTIVE: max(1, min(self.capacity, int(interactive_limit or default_interactive))),
            DBPriority.CRITICAL: max(1, min(self.capacity, int(critical_limit or default_critical))),
            DBPriority.BACKGROUND: max(
                1,
                min(borrower_capacity, int(background_limit or borrower_capacity)),
            ),
            DBPriority.ANALYTICS: max(
                1,
                min(borrower_capacity, int(analytics_limit or borrower_capacity)),
            ),
        }
        self._condition = threading.Condition()
        self._active = {priority: 0 for priority in DBPriority}
        self._queues = {priority: deque() for priority in DBPriority}
        self._waiting = {priority: 0 for priority in DBPriority}
        self._metrics: dict[DBPriority, dict[str, int | float]] = {
            priority: {
                "acquired": 0,
                "timeouts": 0,
                "dropped": 0,
                "deferred": 0,
                "cancelled": 0,
                "wait_seconds_total": 0.0,
                "transaction_seconds_total": 0.0,
            }
            for priority in DBPriority
        }

    @staticmethod
    def normalize(priority: DBPriority | str) -> DBPriority:
        if isinstance(priority, DBPriority):
            return priority
        try:
            return DBPriority(str(priority).strip().lower())
        except (TypeError, ValueError) as exc:
            choices = ", ".join(item.value for item in DBPriority)
            raise ValueError(f"Unknown DB priority {priority!r}; expected one of: {choices}") from exc

    def _foreground_pressure(self) -> bool:
        foreground = (DBPriority.INTERACTIVE, DBPriority.CRITICAL)
        return any(self._active[item] or self._waiting[item] for item in foreground)

    def _can_admit(self, priority: DBPriority, token: object) -> bool:
        if priority is DBPriority.ANALYTICS and not self.analytics_enabled:
            return False
        # Same-priority work is FIFO. Without this check a task that just
        # released the lane can repeatedly reacquire it and starve older waits.
        if not self._queues[priority] or self._queues[priority][0] is not token:
            return False
        total_active = sum(self._active.values())
        if total_active >= self.capacity:
            return False
        if self._active[priority] >= self.limits[priority]:
            return False
        if priority in (DBPriority.BACKGROUND, DBPriority.ANALYTICS):
            # Borrowers may use only the non-reserved portion of a larger pool.
            # This preserves immediate capacity for Telegram commands, delivery
            # proofs and outcome transitions without disabling all maintenance
            # work whenever one foreground session is active. With a two-slot
            # pool this reduces to the previous strict behaviour.
            borrower_ceiling = max(0, self.capacity - self.foreground_reserve)
            if total_active >= borrower_ceiling:
                return False
            if self._foreground_pressure():
                free_slots = self.capacity - total_active
                if free_slots <= self.foreground_reserve:
                    return False
            # Background and analytics are separate heavy-work lanes. Mixing
            # them makes analytics capable of delaying operational jobs.
            if priority is DBPriority.BACKGROUND:
                if self._active[DBPriority.ANALYTICS]:
                    return False
            elif (
                self._active[DBPriority.BACKGROUND]
                or self._waiting[DBPriority.BACKGROUND]
            ):
                return False
        return True

    def acquire(
        self,
        priority: DBPriority | str,
        *,
        timeout_s: float,
        nonblocking: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        priority = self.normalize(priority)
        token = object()
        started = time.monotonic()
        timeout_s = max(0.0, float(timeout_s))
        deadline = started + timeout_s

        with self._condition:
            self._queues[priority].append(token)
            self._waiting[priority] += 1
            try:
                while not self._can_admit(priority, token):
                    if cancel_event is not None and cancel_event.is_set():
                        self._metrics[priority]["cancelled"] += 1
                        return False
                    remaining = deadline - time.monotonic()
                    if nonblocking or remaining <= 0:
                        metric = (
                            "deferred"
                            if priority in (DBPriority.BACKGROUND, DBPriority.ANALYTICS)
                            else "timeouts"
                        )
                        self._metrics[priority][metric] += 1
                        return False
                    self._condition.wait(timeout=min(remaining, 0.05))

                if cancel_event is not None and cancel_event.is_set():
                    self._metrics[priority]["cancelled"] += 1
                    return False
                self._active[priority] += 1
                self._metrics[priority]["acquired"] += 1
                self._queues[priority].popleft()
                self._metrics[priority]["wait_seconds_total"] += max(
                    0.0, time.monotonic() - started
                )
                return True
            finally:
                self._waiting[priority] = max(0, self._waiting[priority] - 1)
                self._condition.notify_all()
                queue = self._queues[priority]
                if token in queue:
                    queue.remove(token)

    def release(self, priority: DBPriority | str, *, held_seconds: float = 0.0) -> None:
        priority = self.normalize(priority)
        with self._condition:
            if self._active[priority] <= 0:
                raise RuntimeError(f"DB admission release without acquire: {priority.value}")
            self._active[priority] -= 1
            self._metrics[priority]["transaction_seconds_total"] += max(
                0.0, float(held_seconds)
            )
            self._condition.notify_all()

    def record_dropped(self, priority: DBPriority | str) -> None:
        priority = self.normalize(priority)
        with self._condition:
            self._metrics[priority]["dropped"] += 1

    def record_deferred(self, priority: DBPriority | str) -> None:
        priority = self.normalize(priority)
        with self._condition:
            self._metrics[priority]["deferred"] += 1

    def record_timeout(self, priority: DBPriority | str) -> None:
        priority = self.normalize(priority)
        with self._condition:
            self._metrics[priority]["timeouts"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            classes: dict[str, dict[str, int | float]] = {}
            for priority in DBPriority:
                metrics = dict(self._metrics[priority])
                metrics["active"] = int(self._active[priority])
                metrics["waiting"] = int(self._waiting[priority])
                metrics["limit"] = int(self.limits[priority])
                classes[priority.value] = metrics
            return {
                "capacity": int(self.capacity),
                "analytics_enabled": bool(self.analytics_enabled),
                "foreground_reserve": int(self.foreground_reserve),
                "active_total": int(sum(self._active.values())),
                "waiting_total": int(sum(self._waiting.values())),
                "classes": classes,
            }
