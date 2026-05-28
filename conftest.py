import os
import asyncio

# Keep pytest runs hermetic and avoid import-time daemon workers that can race
# with the test runner or hit live services in smoke tests.
os.environ.setdefault("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")


async def _inline_to_thread(func, /, *args, **kwargs):
	return func(*args, **kwargs)


if os.environ.get("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1").strip().lower() in {"1", "true", "yes", "y", "on"}:
	asyncio.to_thread = _inline_to_thread
