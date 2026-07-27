"""Pure configuration helpers for Telegram webhook registration."""

from __future__ import annotations

import os

_DEFAULT_ALLOWED_UPDATES = (
    "message,edited_message,callback_query,my_chat_member,chat_member,"
    "pre_checkout_query,shipping_query"
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def telegram_allowed_updates() -> list[str]:
    """Return explicit update types so stale Bot API state cannot filter messages."""
    raw = str(os.getenv("TELEGRAM_ALLOWED_UPDATES") or _DEFAULT_ALLOWED_UPDATES)
    allowed: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if value and value not in allowed:
            allowed.append(value)
    return allowed or ["message", "callback_query"]


def telegram_webhook_registration_kwargs() -> dict[str, object]:
    """Build safe setWebhook arguments while preserving pending updates by default."""
    secret = str(os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    try:
        max_connections = int(os.getenv("TELEGRAM_WEBHOOK_MAX_CONNECTIONS", "20") or 20)
    except (TypeError, ValueError):
        max_connections = 20
    kwargs: dict[str, object] = {
        "allowed_updates": telegram_allowed_updates(),
        "drop_pending_updates": _env_bool(
            "TELEGRAM_DROP_PENDING_UPDATES_ON_STARTUP", False
        ),
        "max_connections": max(1, min(100, max_connections)),
    }
    if secret:
        kwargs["secret_token"] = secret
    return kwargs
