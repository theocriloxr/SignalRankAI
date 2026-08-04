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
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "SafetyFlags":
        source = environ if environ is not None else os.environ

        def _flag(name: str, default: bool = False) -> bool:
            raw = source.get(name)
            if raw is None:
                return bool(default)
            return str(raw).strip().lower() in TRUE_VALUES

        return cls(
            real_execution_enabled=_flag("REAL_EXECUTION_ENABLED"),
            auto_execution_enabled=_flag("AUTO_EXECUTION_ENABLED"),
            auto_trade_enabled=_flag("AUTO_TRADE_ENABLED"),
            copy_trade_enabled=_flag("COPY_TRADE_ENABLED"),
            mt5_live_accounts_enabled=_flag("MT5_ALLOW_LIVE_ACCOUNTS"),
            bybit_execution_enabled=_flag("BYBIT_EXECUTION_ENABLED"),
            real_payouts_enabled=_flag("REAL_PAYOUTS_ENABLED"),
            payments_enabled=_flag("PAYMENTS_ENABLED"),
            telegram_rich_messages_enabled=_flag("TELEGRAM_RICH_MESSAGES_ENABLED"),
            vip_webhook_dispatch_enabled=_flag("VIP_WEBHOOK_DISPATCH_ENABLED"),
            chat_mt5_credentials_enabled=_flag("CHAT_MT5_CREDENTIALS_ENABLED"),
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
