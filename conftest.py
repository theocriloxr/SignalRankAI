"""Root pytest configuration."""
import pytest


def pytest_configure(config):
    """Register asyncio_mode so pytest-asyncio handles async test functions."""
    try:
        config.addinivalue_line(
            "markers",
            "asyncio: mark test as an asyncio coroutine",
        )
    except Exception:
        pass
