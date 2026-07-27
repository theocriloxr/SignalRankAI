from __future__ import annotations

from core.telegram_webhook_config import (
    telegram_allowed_updates,
    telegram_webhook_registration_kwargs,
)


def test_webhook_registration_preserves_pending_updates(monkeypatch):
    monkeypatch.delenv("TELEGRAM_DROP_PENDING_UPDATES_ON_STARTUP", raising=False)
    kwargs = telegram_webhook_registration_kwargs()
    assert kwargs["drop_pending_updates"] is False


def test_webhook_registration_explicitly_accepts_messages_and_callbacks(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_UPDATES", raising=False)
    kwargs = telegram_webhook_registration_kwargs()
    assert "message" in kwargs["allowed_updates"]
    assert "callback_query" in kwargs["allowed_updates"]


def test_destructive_drop_requires_explicit_override(monkeypatch):
    monkeypatch.setenv("TELEGRAM_DROP_PENDING_UPDATES_ON_STARTUP", "1")
    kwargs = telegram_webhook_registration_kwargs()
    assert kwargs["drop_pending_updates"] is True


def test_allowed_updates_are_deduplicated(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_UPDATES", "message,callback_query,message")
    assert telegram_allowed_updates() == ["message", "callback_query"]


def test_webhook_max_connections_is_clamped(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_MAX_CONNECTIONS", "999")
    assert telegram_webhook_registration_kwargs()["max_connections"] == 100
