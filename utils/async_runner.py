from __future__ import annotations

import asyncio
import threading
from typing import Any


_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None
_bg_ready = threading.Event()
_bg_lock = threading.Lock()


def _ensure_background_loop() -> asyncio.AbstractEventLoop:
    """Create (once) and return a dedicated background event loop.

    This avoids creating many short-lived loops/threads when `run_sync()` is
    called from code that already has a running event loop (common in scheduler
    callbacks). Reusing one loop significantly reduces cross-loop resource
    finalization issues with async DB drivers.
    """
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is not None and _bg_thread is not None and _bg_thread.is_alive():
            return _bg_loop

        _bg_ready.clear()

        def _loop_thread_target() -> None:
            global _bg_loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _bg_loop = loop
            _bg_ready.set()
            loop.run_forever()

        _bg_thread = threading.Thread(
            target=_loop_thread_target,
            name="signalrank-run-sync-loop",
            daemon=True,
        )
        _bg_thread.start()

    if not _bg_ready.wait(timeout=5.0) or _bg_loop is None:
        raise RuntimeError("run_sync: failed to initialize background event loop")

    return _bg_loop


def run_sync(coro, timeout: float = 30.0) -> Any:
    """Run an async coroutine from sync code safely.

    - If there's no running event loop, uses `asyncio.run`.
    - If an event loop is already running, runs the coroutine in a new
      background thread with its own event loop and returns the result.

    This is a pragmatic shim to avoid crashes from calling `asyncio.run`
    while an event loop is active. It is not a perfect substitute for
    refactoring callers to be async-aware, but reduces immediate runtime
    failures.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread — safe to use asyncio.run
        return asyncio.run(coro)

    # Event loop is already running in this thread. Execute on a dedicated,
    # long-lived background loop and block for the result.
    bg_loop = _ensure_background_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, bg_loop)
    try:
        return fut.result(timeout=timeout)
    except Exception:
        # Best effort cancellation on timeout/error.
        try:
            fut.cancel()
        except Exception:
            pass
        raise
