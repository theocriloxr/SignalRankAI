"""Canonical environment and feature-mode capability resolver.

Single source of truth for *environment identity* versus *feature activation*
across every service (front door, engine, worker, migration, web). It composes
typed, redacted decisions from the repository's canonical building blocks:

- ``core.env`` — environment name and safety flags
- ``payments.payment_config`` — Paystack mode and checkout policy
- ``execution`` / financial-activation flags — trading and payout mode

The resolver never exposes secret values. Every field is a bool, an enum-ish
string, or a ``safe_reasons`` list of machine-readable reasons.

This is the parity contract: staging and production must resolve the *same*
product capabilities with environment-specific dependency modes (test payments,
paper trading, isolated bots), not reduced feature sets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

from core.env import SafetyFlags, env_bool
from payments.payment_config import resolve_paystack_configuration


def _runtime_environment(environ: Mapping[str, str]) -> str:
    raw = str(
        environ.get("RAILWAY_ENVIRONMENT_NAME")
        or environ.get("RAILWAY_ENVIRONMENT")
        or environ.get("APP_ENV")
        or environ.get("ENVIRONMENT")
        or "dev"
    ).strip().lower()
    aliases = {"prod": "production", "development": "dev", "preview": "staging"}
    return aliases.get(raw, raw or "dev")

_SERVICE_ALIASES = {
    "frontdoor": "frontdoor",
    "front-door": "frontdoor",
    "bot": "frontdoor",
    "engine": "engine",
    "worker": "worker",
    "migration": "migration",
    "migrate": "migration",
    "web": "web",
    "api": "web",
    "all": "all",
}

VALID_SERVICE_ROLES = ("all", "frontdoor", "engine", "worker", "migration", "web")


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """Redacted, typed capability decisions for the active runtime."""

    environment: str
    service_role: str
    payments_enabled: bool
    payments_mode: str  # test | live | unavailable | mismatch
    payments_public_enabled: bool
    paystack_recovery_enabled: bool
    telegram_mode: str  # staging_bot | production_bot | no_token
    trading_mode: str  # paper | testnet | live_disabled | live_guarded
    payout_mode: str  # disabled | sandbox | live_guarded
    provider_mode_by_asset_class: dict[str, str]
    feature_flags: dict[str, bool]
    migration_expected: str | None = None
    migration_current: str | None = None
    readiness: str = "pass"  # pass | fail | unknown
    safe_reasons: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "service_role": self.service_role,
            "payments_enabled": self.payments_enabled,
            "payments_mode": self.payments_mode,
            "payments_public_enabled": self.payments_public_enabled,
            "paystack_recovery_enabled": self.paystack_recovery_enabled,
            "telegram_mode": self.telegram_mode,
            "trading_mode": self.trading_mode,
            "payout_mode": self.payout_mode,
            "provider_mode_by_asset_class": self.provider_mode_by_asset_class,
            "feature_flags": self.feature_flags,
            "migration_expected": self.migration_expected,
            "migration_current": self.migration_current,
            "readiness": self.readiness,
            "safe_reasons": list(self.safe_reasons),
        }


def service_role(environ: Mapping[str, str] | None = None) -> str:
    """Resolve the deployment service role from RUN_MODE/SERVICE_ROLE."""
    env = environ if environ is not None else os.environ
    raw = str(env.get("RUN_MODE") or env.get("SERVICE_ROLE") or "all").strip().lower()
    resolved = _SERVICE_ALIASES.get(raw, raw)
    return resolved if resolved in VALID_SERVICE_ROLES else "all"


def telegram_mode(environ: Mapping[str, str] | None = None) -> str:
    """Determine which Telegram bot identity this environment uses.

    Staging and production must use separate bot tokens so neither environment
    can overwrite the other's webhook. A staging environment with the shared
    production token is a configuration defect and is reported as such.
    """
    env = environ if environ is not None else os.environ
    runtime_env = _runtime_environment(env)
    token = str(env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    staging_token = str(env.get("STAGING_TELEGRAM_BOT_TOKEN") or "").strip()
    if runtime_env == "production":
        if staging_token and not token:
            return "misconfigured"  # production must not run on the staging token
        return "production_bot" if token else "no_token"
    if runtime_env == "staging":
        # Staging must use its own token. Falling back to the shared
        # TELEGRAM_BOT_TOKEN would let staging attach the production bot and
        # overwrite its webhook — a parity violation, so fail closed.
        if staging_token:
            return "staging_bot"
        if token:
            return "misconfigured"
        return "no_token"
    return "staging_bot" if staging_token else ("staging_bot" if token else "no_token")


def trading_mode(
    flags: SafetyFlags | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the safe execution mode.

    paper/testnet are the safe defaults; live requires the repository's guarded
    activation contract (REAL_EXECUTION_ENABLED plus the financial-activation
    dependency checks enforced elsewhere).
    """
    env = environ if environ is not None else os.environ
    flags = flags if flags is not None else SafetyFlags.from_env(environ=env)
    if flags.real_execution_enabled:
        return "live_guarded"
    if flags.auto_execution_enabled or flags.auto_trade_enabled or flags.copy_trade_enabled:
        return "live_guarded" if _live_activation_valid(env) else "live_disabled"
    bybit_testnet = env_bool("BYBIT_TESTNET", True) if environ is None else _raw_bool(env, "BYBIT_TESTNET", True)
    paper_enabled = env_bool("PAPER_TRADING_ENABLED", True) if environ is None else _raw_bool(env, "PAPER_TRADING_ENABLED", True)
    if paper_enabled:
        return "paper"
    return "testnet" if bybit_testnet else "live_disabled"


def _live_activation_valid(environ: Mapping[str, str]) -> bool:
    try:
        from core.financial_activation import evaluate_financial_activation

        return bool(evaluate_financial_activation(environ=environ).ok)
    except Exception:
        return False


def payout_mode(
    flags: SafetyFlags | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = environ if environ is not None else os.environ
    flags = flags if flags is not None else SafetyFlags.from_env(environ=env)
    if not flags.real_payouts_enabled:
        return "disabled"
    return "live_guarded"


def provider_mode_by_asset_class(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Report dependency mode per asset class without exposing credentials."""
    env = environ if environ is not None else os.environ
    result: dict[str, str] = {}
    for asset_class, probe in (
        ("crypto", "BTCUSDT"),
        ("fx", "EURUSD"),
        ("commodity", "XAGUSD"),
        ("stock", "AAPL"),
        ("index", "US500"),
    ):
        try:
            from data.get_live_price import _get_providers_for_asset

            providers = list(_get_providers_for_asset(probe))
            if not providers:
                result[asset_class] = "unconfigured"
            elif all(provider == "yahoo" for provider in providers):
                result[asset_class] = "public_only"
            else:
                result[asset_class] = "configured"
        except Exception:
            result[asset_class] = "unknown"
    return result


def _raw_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def feature_flags(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Typed public feature-flag snapshot (safe booleans only)."""
    env = environ if environ is not None else os.environ
    flags = SafetyFlags.from_env(environ=env)
    return {
        "paper_trading_enabled": _raw_bool(env, "PAPER_TRADING_ENABLED", True),
        "news_enabled": _raw_bool(env, "ENABLE_NEWS", True),
        "ml_enabled": _raw_bool(env, "ENABLE_ML", True),
        "adaptive_strategy_enabled": _raw_bool(env, "ADAPTIVE_STRATEGY_ENGINE_ENABLED", True),
        "outcome_tracker_enabled": _raw_bool(env, "REALTIME_OUTCOME_TRACKER_ENABLED", True),
        "payments_enabled": flags.payments_enabled,
        "real_execution_enabled": flags.real_execution_enabled,
        "real_payouts_enabled": flags.real_payouts_enabled,
        "copy_trade_enabled": flags.copy_trade_enabled,
    }


def migration_revisions() -> tuple[str | None, str | None]:
    """Return (expected_head, current_head) without a database connection.

    Expected head is derived from the Alembic script directory. Current head is
    read from a locally mounted alembic_version only when a DB engine exists;
    otherwise it stays None (services report it at runtime via readiness).
    """
    expected: str | None = None
    try:
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parents[1]
        cfg = Config(str(root / "alembic.ini"))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        if len(heads) == 1:
            expected = heads[0]
    except Exception:
        expected = None
    return expected, None


def resolve_capabilities(
    environ: Mapping[str, str] | None = None,
) -> CapabilityReport:
    """Resolve the full redacted capability report for the active runtime."""
    env = environ if environ is not None else os.environ
    runtime_env = _runtime_environment(env)
    flags = SafetyFlags.from_env(environ=env)
    paystack = resolve_paystack_configuration(environ=env)

    payments_mode = "unavailable"
    if paystack.key_mode == "test":
        payments_mode = "test"
    elif paystack.key_mode == "live":
        payments_mode = "live"
    elif paystack.key_mode == "mismatch":
        payments_mode = "mismatch"

    reasons: list[str] = []
    if not paystack.payments_enabled:
        reasons.append("payments_disabled")
    if paystack.key_mode == "missing":
        reasons.append("paystack_secret_missing")
    if paystack.key_mode == "mismatch":
        reasons.append("paystack_key_mode_mismatch")
    if paystack.key_mode == "invalid":
        reasons.append("unsupported_paystack_key_mode")
    if runtime_env == "production" and paystack.key_mode == "test":
        reasons.append("test_key_in_production")

    expected_head, current_head = migration_revisions()
    readiness = "pass"
    if runtime_env == "production" and not paystack.payments_enabled and env_bool(
        "PAYMENTS_REQUIRED_IN_PRODUCTION", False
    ):
        readiness = "fail"
        reasons.append("payments_required_in_production_but_disabled")

    return CapabilityReport(
        environment=runtime_env,
        service_role=service_role(environ=env),
        payments_enabled=paystack.payments_enabled,
        payments_mode=payments_mode,
        payments_public_enabled=paystack.payments_public_enabled,
        paystack_recovery_enabled=paystack.webhook_recovery_enabled,
        telegram_mode=telegram_mode(environ=env),
        trading_mode=trading_mode(flags=flags, environ=env),
        payout_mode=payout_mode(flags=flags, environ=env),
        provider_mode_by_asset_class=provider_mode_by_asset_class(environ=env),
        feature_flags=feature_flags(environ=env),
        migration_expected=expected_head,
        migration_current=current_head,
        readiness=readiness,
        safe_reasons=tuple(reasons),
    )


__all__ = [
    "CapabilityReport",
    "feature_flags",
    "migration_revisions",
    "payout_mode",
    "provider_mode_by_asset_class",
    "resolve_capabilities",
    "service_role",
    "telegram_mode",
    "trading_mode",
]
