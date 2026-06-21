import os
import asyncio
from pathlib import Path

import pytest

# Keep pytest runs hermetic and avoid import-time daemon workers that can race
# with the test runner or hit live services in smoke tests.
os.environ.setdefault("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")


async def _inline_to_thread(func, /, *args, **kwargs):
	return func(*args, **kwargs)


if os.environ.get("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1").strip().lower() in {"1", "true", "yes", "y", "on"}:
	asyncio.to_thread = _inline_to_thread


_IGNORED_MANUAL_TESTS = {
	"test_market_data_manual.py",
	"test_batch_engine.py",
	"test_batch_v2.py",
	"test_signals_diag.py",
	"test_strategy_debug.py",
}


def pytest_ignore_collect(collection_path, config):
	path = Path(str(collection_path))
	return path.name in _IGNORED_MANUAL_TESTS


def pytest_collection_modifyitems(config, items):
	for item in items:
		try:
			obj = getattr(item, "obj", None)
			if obj is not None and asyncio.iscoroutinefunction(obj):
				item.add_marker(pytest.mark.asyncio)
		except Exception:
			continue
