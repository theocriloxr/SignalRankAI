from __future__ import annotations

from pathlib import Path

from signalrank_telegram.telegram_errors import permanent_telegram_send_error


ROOT = Path(__file__).resolve().parents[1]


def test_permanent_telegram_error_classification() -> None:
    assert permanent_telegram_send_error(RuntimeError("Bad Request: Chat not found")) == "chat_not_found"
    assert permanent_telegram_send_error(RuntimeError("Forbidden: bot was blocked by the user")) == "bot_blocked"
    assert permanent_telegram_send_error(RuntimeError("User is deactivated")) == "user_deactivated"
    assert permanent_telegram_send_error(RuntimeError("temporary upstream failure")) is None


def test_remediation_uses_synchronous_session_api() -> None:
    source = (ROOT / "db" / "staging_remediation.py").read_text(encoding="utf-8")
    assert "get_sync_session" in source
    assert "with get_session()" not in source
    assert "session_scope" not in source


def test_outcome_recipients_exclude_unreachable_users() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    assert "User.telegram_reachable.is_(True)" in source
    assert "User.notification_suppressed.is_(False)" in source
