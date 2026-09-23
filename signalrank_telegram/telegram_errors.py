"""Stable Telegram error classification shared by delivery paths."""
from __future__ import annotations

from typing import Optional


_PERMANENT_SEND_ERRORS = (
    ("bot was blocked", "bot_blocked"),
    ("blocked by the user", "bot_blocked"),
    ("chat not found", "chat_not_found"),
    ("user is deactivated", "user_deactivated"),
    ("chat not accessible", "chat_not_accessible"),
    ("bot can't initiate conversation", "bot_cannot_initiate"),
    ("bot can\u2019t initiate conversation", "bot_cannot_initiate"),
)


def permanent_telegram_send_error(exc: BaseException) -> Optional[str]:
    """Return a durable reason for a non-retryable Telegram send failure."""
    message = str(exc or "").strip().lower()
    for token, reason in _PERMANENT_SEND_ERRORS:
        if token in message:
            return reason
    return None


__all__ = ["permanent_telegram_send_error"]
