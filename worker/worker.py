import asyncio
import contextlib
import os
import signal
import threading
from typing import Optional

from db.session import ENGINE, get_session
from db.repository import expire_subscriptions


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


class Worker:
    """Async worker process skeleton.

    Responsibilities (to be implemented incrementally):
    - Poll market data / consume WS ticks
    - Run strategy engine
    - Call engine.signal_controller.SignalController to approve + persist + dispatch
    - Run outcome tracking loop
    """

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self.dry_run = _env_bool("DRY_RUN", True)

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        expiry_task = asyncio.create_task(self._expiry_loop())
        ws_task: Optional[asyncio.Task] = None

        if _env_bool("CRYPTO_WS_ENABLED", False):
            try:
                from data.ws_ingest import run_ws_ingestor

                ws_task = asyncio.create_task(run_ws_ingestor(self._stop))
            except Exception:
                ws_task = None
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
        finally:
            if ws_task is not None:
                ws_task.cancel()
                with contextlib.suppress(Exception):
                    await ws_task
            expiry_task.cancel()
            with contextlib.suppress(Exception):
                await expiry_task

    async def _expiry_loop(self) -> None:
        # Runs periodically; safe no-op when DATABASE_URL not configured.
        while not self._stop.is_set():
            try:
                if ENGINE is not None:
                    async with get_session() as session:
                        _ = await expire_subscriptions(session)
                        await session.commit()
            except Exception:
                # Keep worker alive; production version should log structured errors.
                pass
            await asyncio.sleep(3600)


async def _amain() -> None:
    worker = Worker()

    loop = asyncio.get_running_loop()

    def _handle_sig(*_: object) -> None:
        worker.request_stop()

    # NOTE: `loop.add_signal_handler` only works in the main thread on Unix.
    # In RUN_MODE=all we run the worker in a background thread, so skip
    # installing signal handlers there.
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_sig)
            except NotImplementedError:
                # Windows event loop may not support add_signal_handler
                pass

    await worker.run()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
