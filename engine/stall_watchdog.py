"""Detect an engine loop that is alive but no longer making progress.

Production evidence (read-only Railway logs, 28 Oct 2026): the engine logged
its last pipeline step at 2026-10-22 08:08:30 UTC, seconds before Postgres was
redeployed and the engine's database connections broke. The process stayed up,
so Railway kept reporting the service Online while no cycle ran for six days.
Five database calls in the loop then went through ``run_sync`` without a
timeout, so one call on a dead connection could block the loop thread forever;
they are bounded by ``ENGINE_DB_CALL_TIMEOUT_SECONDS`` since 29 Oct. The
watchdog stays as the backstop for any other way the loop can stop.

The watchdog cannot unblock a stuck thread. It records the loop's progress; when
nothing has progressed for ``ENGINE_STALL_SECONDS`` it logs the loop thread's
stack (naming the call that hung), publishes a ``stalled`` heartbeat that
readiness treats as not ready, and, for a dedicated engine process, exits with
code 70 so the platform restart policy starts a fresh engine. A process that
also serves HTTP is never terminated; it only alerts.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from typing import Callable

logger = logging.getLogger("engine.stall_watchdog")

EXIT_CODE = 70
_lock = threading.Lock()
_state = {"at": time.monotonic(), "stage": "starting", "thread_id": None}
_started = False


def mark(stage: str) -> None:
    """Record that the engine loop made progress at ``stage``."""
    with _lock:
        _state["at"] = time.monotonic()
        _state["stage"] = str(stage)[:96]
        _state["thread_id"] = threading.get_ident()


def snapshot() -> dict:
    with _lock:
        return {"age_seconds": time.monotonic() - _state["at"], "stage": _state["stage"],
                "thread_id": _state["thread_id"]}


def stall_seconds() -> float:
    try:
        return max(120.0, float(os.getenv("ENGINE_STALL_SECONDS", "900") or 900))
    except ValueError:
        return 900.0


def stall_action() -> str:
    explicit = str(os.getenv("ENGINE_STALL_ACTION") or "").strip().lower()
    if explicit in {"exit", "alert"}:
        return explicit
    if "railway_main" in sys.modules:
        return "alert"  # the engine shares this process with the HTTP service
    try:
        from runtime.roles import RunMode, infer_run_mode

        return "exit" if infer_run_mode() is RunMode.ENGINE else "alert"
    except Exception:
        return "alert"


def thread_stack(thread_id: int | None) -> str:
    frame = sys._current_frames().get(thread_id) if thread_id else None
    return "".join(traceback.format_stack(frame)) if frame is not None else "unavailable"


def check(publish: Callable[[dict], None] | None = None, exit_fn: Callable[[int], None] = os._exit) -> bool:
    """One watchdog evaluation; returns True when a stall was reported."""
    state = snapshot()
    limit = stall_seconds()
    if state["age_seconds"] < limit:
        return False
    action = stall_action()
    stack = thread_stack(state["thread_id"])
    logger.critical("[engine_stall] no progress for %.0fs (limit %.0fs) at stage=%s action=%s\n%s",
                    state["age_seconds"], limit, state["stage"], action, stack)
    if publish is not None:
        try:
            publish({"status": "stalled", "stall_stage": state["stage"],
                     "stall_age_seconds": round(state["age_seconds"]), "stall_action": action})
        except Exception:
            logger.debug("[engine_stall] could not publish stalled state", exc_info=True)
    if action == "exit":
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        exit_fn(EXIT_CODE)
    return True


def start(publish: Callable[[dict], None] | None = None, interval_seconds: float = 30.0) -> bool:
    """Start the daemon watchdog once per process."""
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    mark("watchdog_started")

    def _run() -> None:
        reported_at = None
        while True:
            time.sleep(interval_seconds)
            current = snapshot()["stage"], _state["at"]
            if reported_at == current:
                continue  # alert once per stall; a new mark() re-arms the watchdog
            if check(publish):
                reported_at = current

    threading.Thread(target=_run, name="engine-stall-watchdog", daemon=True).start()
    return True


__all__ = ["EXIT_CODE", "check", "mark", "snapshot", "stall_action", "stall_seconds", "start", "thread_stack"]
