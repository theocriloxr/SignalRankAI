"""Typed environment parsing and safe feature defaults."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping


TRUE_VALUES = frozenset({"1", "true", "yes", "y", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "n", "off", ""})


_BOOL_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ENABLE_ML", "ML_ENABLED"),
    ("INDEX_ENABLED", "INDICES_ENABLED"),
)
# Secret aliases may intentionally coexist during credential rotation. Their
# values must never be logged or fingerprinted; consumers choose canonical
# order and validate credentials against the provider.
_SECRET_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("META_API_TOKEN", "METAAPI_TOKEN"),
    ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"),
)


def _normalized_bool_value(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise RuntimeError(f"invalid_boolean_environment_value:{name}")


def validate_alias_conflicts() -> None:
    """Fail startup when equivalent configuration aliases disagree."""
    for group in _BOOL_ALIAS_GROUPS:
        configured = [(name, _normalized_bool_value(name)) for name in group if os.getenv(name) is not None]
        values = {value for _name, value in configured}
        if len(values) > 1:
            raise RuntimeError("conflicting_boolean_environment_aliases:" + ",".join(name for name, _ in configured))
    # Secret aliases are deliberately not compared: dual values can be a safe
    # rotation state and comparing/reporting them creates unnecessary secret
    # handling. Provider authentication decides which candidate is valid.


def sanitized_config_fingerprint(names: Iterable[str]) -> str:
    """Hash only non-secret configuration presence/boolean state, never values."""
    material: list[str] = []
    secret_names = {name for group in _SECRET_ALIAS_GROUPS for name in group}
    for name in sorted({str(n) for n in names}):
        raw = os.getenv(name)
        if name in secret_names:
            state = "present" if bool(str(raw or "").strip()) else "absent"
        elif raw is None:
            state = "unset"
        else:
            normalized = str(raw).strip().lower()
            state = normalized if normalized in TRUE_VALUES | FALSE_VALUES else "set"
        material.append(f"{name}={state}")
    return hashlib.sha256("|".join(material).encode("utf-8")).hexdigest()



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


def env_bool_alias(
    canonical: str,
    *aliases: str,
    default: bool = False,
    strict_conflict: bool | None = None,
) -> bool:
    """Resolve compatibility aliases while rejecting contradictory values.

    In staging/production contradictory aliases are a configuration error by
    default. Local/test environments remain permissive so migration tests can
    explicitly exercise legacy names.
    """
    configured: list[tuple[str, bool]] = []
    for name in (canonical, *aliases):
        if os.getenv(name) is None:
            continue
        configured.append((name, env_bool(name, default)))
    if not configured:
        return bool(default)

    distinct = {value for _, value in configured}
    strict = (
        runtime_environment_name("dev") in {"staging", "production"}
        if strict_conflict is None
        else bool(strict_conflict)
    )
    if strict and len(distinct) > 1:
        names = ",".join(name for name, _ in configured)
        raise RuntimeError(f"conflicting_boolean_aliases:{canonical}:{names}")
    return configured[0][1]


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


def resolve_runtime_environment_name(
    environ: Mapping[str, str],
    default: str = "dev",
) -> str:
    """Resolve environment identity without letting a copied override spoof production.

    Railway environment metadata remains authoritative by default. An isolated
    certification project whose default Railway environment is named production
    may opt into staging semantics only when the staging profile, explicit
    staging override, and exact pinned Railway project ID all agree.
    """
    override = str(environ.get("SIGNALRANK_ENVIRONMENT_OVERRIDE") or "").strip().lower()
    railway_name = str(
        environ.get("RAILWAY_ENVIRONMENT_NAME")
        or environ.get("RAILWAY_ENVIRONMENT")
        or ""
    ).strip().lower()

    if override and railway_name in {"production", "prod"} and override not in {"production", "prod"}:
        profile = str(environ.get("SIGNALRANK_ENV_PROFILE") or "").strip().lower()
        expected_project = str(environ.get("STAGING_CERTIFICATION_PROJECT_ID") or "").strip()
        actual_project = str(environ.get("RAILWAY_PROJECT_ID") or "").strip()
        pinned_staging = (
            override in {"staging", "stage", "preview"}
            and profile == "staging-certification"
            and bool(expected_project)
            and bool(actual_project)
            and hmac.compare_digest(expected_project, actual_project)
        )
        if not pinned_staging:
            override = ""

    raw = (
        str(
            override
            or railway_name
            or environ.get("RAILWAY_ENVIRONMENT_ID")
            or environ.get("APP_ENV")
            or environ.get("ENVIRONMENT")
            or default
        )
        .strip()
        .lower()
    )
    aliases = {"prod": "production", "development": "dev", "preview": "staging", "stage": "staging"}
    return aliases.get(raw, raw or default)


def runtime_environment_name(default: str = "dev") -> str:
    return resolve_runtime_environment_name(os.environ, default)

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
        flags = cls(
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
        flags.validate_invariants()
        return flags

    def validate_invariants(self) -> None:
        """Fail closed on contradictory live-execution safety configuration."""
        violations: list[str] = []
        if self.auto_trade_enabled and not self.auto_execution_enabled:
            violations.append("AUTO_TRADE_ENABLED_requires_AUTO_EXECUTION_ENABLED")
        if self.copy_trade_enabled and not self.auto_execution_enabled:
            violations.append("COPY_TRADE_ENABLED_requires_AUTO_EXECUTION_ENABLED")
        if (
            self.auto_execution_enabled
            or self.auto_trade_enabled
            or self.copy_trade_enabled
            or self.mt5_live_accounts_enabled
            or self.bybit_execution_enabled
        ) and not self.real_execution_enabled:
            violations.append("broker_execution_requires_REAL_EXECUTION_ENABLED")
        if self.real_payouts_enabled and not self.payments_enabled:
            violations.append("REAL_PAYOUTS_ENABLED_requires_PAYMENTS_ENABLED")
        if violations:
            raise RuntimeError("unsafe_safety_flag_configuration:" + ",".join(violations))

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


def financial_feature_flags() -> dict[str, bool]:
    """Return non-secret financial safety state for owner diagnostics."""
    flags = SafetyFlags.from_env()
    return {
        "real_execution_enabled": flags.real_execution_enabled,
        "auto_execution_enabled": flags.auto_execution_enabled,
        "auto_trade_enabled": flags.auto_trade_enabled,
        "copy_trade_enabled": flags.copy_trade_enabled,
        "mt5_live_accounts_enabled": flags.mt5_live_accounts_enabled,
        "bybit_execution_enabled": flags.bybit_execution_enabled,
        "real_payouts_enabled": flags.real_payouts_enabled,
        "payments_enabled": flags.payments_enabled,
    }


def validate_required_secrets(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in names if not secret_present(name))


__all__ = [
    "Environment",
    "SafetyFlags",
    "env_bool",
    "env_bool_alias",
    "env_int",
    "financial_feature_flags",
    "environment",
    "redact_value",
    "runtime_environment_name",
    "sanitized_config_fingerprint",
    "secret_present",
    "validate_alias_conflicts",
    "validate_required_secrets",
]
