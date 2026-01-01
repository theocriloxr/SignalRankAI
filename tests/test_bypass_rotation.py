import os

from core.redis_state import RedisState


def test_unlock_invalidates_when_bypass_key_rotates(monkeypatch):
    # Ensure we use in-memory fallback
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    state = RedisState()

    monkeypatch.setenv("BYPASS_KEY", "old_secret")
    state.set_temp_owner_sync(telegram_user_id=123, ttl_seconds=3600)
    assert state.has_temp_owner_sync(123) is True

    # Rotate bypass key: previously granted access is revoked immediately
    monkeypatch.setenv("BYPASS_KEY", "new_secret")
    assert state.has_temp_owner_sync(123) is False
