from __future__ import annotations

import asyncio
import threading
from typing import Any


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

    # Event loop is running in this thread; run the coroutine in a
    # dedicated thread with its own loop to avoid interfering with the
    # active loop.
    result: dict = {}

    def _thread_target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except Exception as e:  # store exception to re-raise in caller
            result["exc"] = e
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError("run_sync: coroutine did not finish within timeout")
    if "exc" in result:
        raise result["exc"]
    return result.get("value")
