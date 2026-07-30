import asyncio
import sys
import types


async def _check_locked_result(fake_value):
    from engine.signal_lock import is_signal_locked

    class _FakeState:
        @staticmethod
        def has_redis_sync():
            return True

        @staticmethod
        def get_str_sync(_key):
            return fake_value

    original = sys.modules.get("core.redis_state")
    sys.modules["core.redis_state"] = types.SimpleNamespace(state=_FakeState())
    try:
        return await is_signal_locked("BTCUSDT", "long", "1h")
    finally:
        if original is None:
            sys.modules.pop("core.redis_state", None)
        else:
            sys.modules["core.redis_state"] = original


def test_signal_lock_returns_true_when_redis_key_exists():
    assert asyncio.run(_check_locked_result("1")) is True


def test_signal_lock_returns_false_when_redis_key_missing():
    assert asyncio.run(_check_locked_result(None)) is False
