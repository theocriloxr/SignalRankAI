"""Typed environment parsing and safe feature defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


TRUE_VALUES = frozenset({"1", "true", "yes", "y", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "n", "off", ""})


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return bool(default)


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def runtime_environment_name(default: str = "dev") -> str:
    """Return the platform environment used for runtime isolation.

    Railway environment metadata is authoritative when present. This prevents a
    copied APP_ENV=production value from contaminating staging advisory locks,
    ledgers, caches, and delivery scopes.
    """
    raw = str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or default
    ).strip().lower()
    aliases = {"prod": "production", "development": "dev", "preview": "staging"}
    return aliases.get(raw, raw or default)


def environment() -> Environment:
    raw = runtime_environment_name("dev")
    try:
        return Environment(raw)
    except ValueError:
        return Environment.DEV


def secret_present(*names: str) -> bool:
    return any(bool(str(os.getenv(name) or "").strip()) for name in names)


def redact_value(value: object, *, keep: int = 4) -> str:
    raw = str(value or "")
    if not raw:
        return "<unset>"
    if len(raw) <= keep:
        return "<redacted>"
    return f"<redacted>...{raw[-keep:]}"


@dataclass(frozen=True, slots=True)
class SafetyFlags:
    real_execution_enabled: bool = False
    auto_execution_enabled: bool = False
    auto_trade_enabled: bool = False
    copy_trade_enabled: bool = False
    mt5_live_accounts_enabled: bool = False
    bybit_execution_enabled: bool = False
    real_payouts_enabled: bool = False
    payments_enabled: bool = False
    telegram_rich_messages_enabled: bool = False
    vip_webhook_dispatch_enabled: bool = False
    chat_mt5_credentials_enabled: bool = False

    @classmethod
    def from_env(cls) -> "SafetyFlags":
        return cls(
            real_execution_enabled=env_bool("REAL_EXECUTION_ENABLED", False),
            auto_execution_enabled=env_bool("AUTO_EXECUTION_ENABLED", False),
            auto_trade_enabled=env_bool("AUTO_TRADE_ENABLED", False),
            copy_trade_enabled=env_bool("COPY_TRADE_ENABLED", False),
            mt5_live_accounts_enabled=env_bool("MT5_ALLOW_LIVE_ACCOUNTS", False),
            bybit_execution_enabled=env_bool("BYBIT_EXECUTION_ENABLED", False),
            real_payouts_enabled=env_bool("REAL_PAYOUTS_ENABLED", False),
            payments_enabled=env_bool("PAYMENTS_ENABLED", False),
            telegram_rich_messages_enabled=env_bool("TELEGRAM_RICH_MESSAGES_ENABLED", False),
            vip_webhook_dispatch_enabled=env_bool("VIP_WEBHOOK_DISPATCH_ENABLED", False),
            chat_mt5_credentials_enabled=env_bool("CHAT_MT5_CREDENTIALS_ENABLED", False),
        )

    def enabled_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, enabled in (
                ("REAL_EXECUTION_ENABLED", self.real_execution_enabled),
                ("AUTO_EXECUTION_ENABLED", self.auto_execution_enabled),
                ("AUTO_TRADE_ENABLED", self.auto_trade_enabled),
                ("COPY_TRADE_ENABLED", self.copy_trade_enabled),
                ("MT5_ALLOW_LIVE_ACCOUNTS", self.mt5_live_accounts_enabled),
                ("BYBIT_EXECUTION_ENABLED", self.bybit_execution_enabled),
                ("REAL_PAYOUTS_ENABLED", self.real_payouts_enabled),
                ("PAYMENTS_ENABLED", self.payments_enabled),
                ("TELEGRAM_RICH_MESSAGES_ENABLED", self.telegram_rich_messages_enabled),
                ("VIP_WEBHOOK_DISPATCH_ENABLED", self.vip_webhook_dispatch_enabled),
                ("CHAT_MT5_CREDENTIALS_ENABLED", self.chat_mt5_credentials_enabled),
            )
            if enabled
        )


def validate_required_secrets(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in names if not secret_present(name))


__all__ = [
    "Environment",
    "SafetyFlags",
    "env_bool",
    "env_int",
    "environment",
    "redact_value",
    "runtime_environment_name",
    "secret_present",
    "validate_required_secrets",
]
