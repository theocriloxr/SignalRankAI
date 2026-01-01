import asyncio
import contextlib
import os
import signal

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
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
        finally:
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
