"""Early runtime safety and full-system staging-test policy.

This module intentionally depends only on the Python standard library so it can
run before configuration-bearing modules are imported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import MutableMapping

_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_TEST_ACK = "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS"
FULL_SYSTEM_STAGING_TEST_ACK_VALUE = _TEST_ACK

# These capabilities are enabled together only in the explicit staging test
# profile. External integrations must still use sandbox/demo credentials.
_FULL_SYSTEM_FLAGS = (
    "PUBLIC_TESTING_MODE",
    "DEMO_EXECUTION_ENABLED",
    "REAL_EXECUTION_ENABLED",
    "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "BYBIT_EXECUTION_ENABLED",
    "PAYMENTS_ENABLED",
    "PAYMENTS_PUBLIC_ENABLED",
    "PAYMENTS_PUBLIC_TEST_MODE",
    "REAL_PAYOUTS_ENABLED",
    "FREE_SIGNAL_DISTRIBUTION_ENABLED",
    "FREE_RANDOM_DISTRIBUTION_ENABLED",
    "WS_INGEST_ENABLED",
    "WS_CRYPTO_ENABLED",
    "CRYPTO_WS_ENABLED",
    "PAPER_TRADING_ENABLED",
    "PAPER_AUTO_TRADE_DEFAULT_ENABLED",
    "PAPER_AUTO_EXECUTION_ENABLED",
)

# Non-production runs may exercise the whole execution pipeline, but they may
# never cross into a live MT5 account. Bybit and Paystack must remain test-mode.
_NONPRODUCTION_HARD_BOUNDARIES = {
    "MT5_ALLOW_LIVE_ACCOUNTS": "0",
    "BYBIT_TESTNET": "1",
    "PAYMENTS_PUBLIC_TEST_MODE": "1",
}

# Default fail-closed behaviour when full-system testing has not been explicitly
# acknowledged.
_NONPRODUCTION_FORCE_OFF = (
    "REAL_EXECUTION_ENABLED",
    "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "MT5_ALLOW_LIVE_ACCOUNTS",
    "BYBIT_EXECUTION_ENABLED",
    "REAL_PAYOUTS_ENABLED",
    "PAYMENTS_PUBLIC_ENABLED",
    "FREE_SIGNAL_DISTRIBUTION_ENABLED",
    "FREE_RANDOM_DISTRIBUTION_ENABLED",
)


@dataclass(frozen=True)
class RuntimeSafetyResult:
    environment: str
    full_system_test_enabled: bool
    acknowledgement_valid: bool
    forced_on: tuple[str, ...]
    forced_off: tuple[str, ...]
    hard_boundaries: tuple[str, ...]
    audience_allowlist: str


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _normalise_ack(value: object) -> str:
    """Normalise Railway/UI copy-paste variants without weakening the exact token."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def is_full_system_ack_valid(value: object) -> bool:
    return _normalise_ack(value) == _TEST_ACK


def _environment_name(env: MutableMapping[str, str]) -> str:
    return str(
        env.get("APP_ENV")
        or env.get("RAILWAY_ENVIRONMENT_NAME")
        or env.get("RAILWAY_ENVIRONMENT")
        or "dev"
    ).strip().lower()


def apply_runtime_safety_environment(
    environ: MutableMapping[str, str] | None = None,
) -> RuntimeSafetyResult:
    """Apply fail-closed defaults or the acknowledged staging integration mode.

    Full-system staging mode turns on feature paths but keeps the external-money
    boundaries in sandbox/demo mode. Test delivery is restricted to
    ``FULL_SYSTEM_TEST_USER_IDS`` or, when absent, the configured owner IDs.
    """

    env = environ if environ is not None else os.environ
    environment = _environment_name(env)
    if environment in {"production", "prod"}:
        return RuntimeSafetyResult(environment, False, False, (), (), (), str(env.get("DELIVERY_AUDIENCE_ALLOWLIST") or ""))

    requested = _truthy(env.get("FULL_SYSTEM_STAGING_TEST_MODE"))
    ack_valid = is_full_system_ack_valid(env.get("FULL_SYSTEM_STAGING_TEST_ACK"))
    enabled = bool(requested and ack_valid)
    forced_on: list[str] = []
    forced_off: list[str] = []
    boundaries: list[str] = []

    if enabled:
        for name in _FULL_SYSTEM_FLAGS:
            if not _truthy(env.get(name)):
                forced_on.append(name)
            env[name] = "1"

        for name, value in _NONPRODUCTION_HARD_BOUNDARIES.items():
            if str(env.get(name) or "").strip() != value:
                boundaries.append(name)
            env[name] = value

        # A stale live Paystack key must never survive into staging. Missing keys
        # are left enabled so diagnostics expose the configuration gap; an
        # explicitly live key fails the money-moving paths closed.
        paystack_key = str(env.get("PAYSTACK_SECRET_KEY") or "").strip()
        if paystack_key and not paystack_key.startswith("sk_test_"):
            for name in ("PAYMENTS_ENABLED", "PAYMENTS_PUBLIC_ENABLED", "REAL_PAYOUTS_ENABLED"):
                if _truthy(env.get(name)):
                    forced_off.append(name)
                env[name] = "0"
            boundaries.append("PAYSTACK_LIVE_KEY_REJECTED")

        # Restrict all generated/resend traffic to explicit test users. This
        # still exercises free-tier and multi-user paths without broadcasting to
        # the complete production user table.
        test_users = str(env.get("FULL_SYSTEM_TEST_USER_IDS") or "").strip()
        if not test_users:
            test_users = str(
                env.get("OWNER_TELEGRAM_ID")
                or env.get("TELEGRAM_OWNER_ID")
                or env.get("OWNER_IDS")
                or ""
            ).strip()
        if test_users:
            env["DELIVERY_AUDIENCE_ALLOWLIST"] = test_users
            env["RESEND_AUDIENCE_ALLOWLIST_ONLY"] = "1"

        # Proxy validation is meaningful only when a provider is configured.
        proxy_configured = any(
            str(env.get(name) or "").strip()
            for name in ("WEBSHARE_PROXY_URL", "PROXY_PROVIDER_URL", "PROXY_URL")
        )
        env["PROXY_VALIDATION_ENABLED"] = "1" if proxy_configured else "0"
    else:
        for name in _NONPRODUCTION_FORCE_OFF:
            if _truthy(env.get(name)):
                forced_off.append(name)
            env[name] = "0"

    return RuntimeSafetyResult(
        environment=environment,
        full_system_test_enabled=enabled,
        acknowledgement_valid=ack_valid,
        forced_on=tuple(forced_on),
        forced_off=tuple(forced_off),
        hard_boundaries=tuple(boundaries),
        audience_allowlist=str(env.get("DELIVERY_AUDIENCE_ALLOWLIST") or ""),
    )


__all__ = ["RuntimeSafetyResult", "FULL_SYSTEM_STAGING_TEST_ACK_VALUE", "apply_runtime_safety_environment", "is_full_system_ack_valid"]
