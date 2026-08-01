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
_PAYSTACK_LIVE_ACK = "I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY"
FULL_SYSTEM_STAGING_TEST_ACK_VALUE = _TEST_ACK
PAYSTACK_LIVE_STAGING_ACK_VALUE = _PAYSTACK_LIVE_ACK


def _clean_paystack_key(value: object) -> str:
    """Normalise a Railway secret without ever logging its contents."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"\"", "'"}:
        text = text[1:-1].strip()
    return text

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
# never cross into a live MT5 account and Bybit remains testnet. Paystack
# may use guarded live mode only after a second explicit acknowledgement.
_NONPRODUCTION_HARD_BOUNDARIES = {
    "MT5_ALLOW_LIVE_ACCOUNTS": "0",
    "BYBIT_TESTNET": "1",
    "REAL_PAYOUTS_ENABLED": "0",
    "PAYSTACK_LIVE_STAGING_ENABLED": "0",
    "PAYMENTS_PUBLIC_TEST_MODE": "1",
}

# Operational settings required for an end-to-end staging proof. These are not
# live-money permissions; they ensure the enabled workers are actually admitted
# to the small Railway database pool and that rejected quality decisions remain
# observable while allowlisted test delivery continues.
_FULL_SYSTEM_OPERATIONAL_SETTINGS = {
    "PAPER_WORKER_DB_PRIORITY": "interactive",
    "PAPER_DB_TIMEOUT_SECONDS": "12",
    "ADAPTIVE_CANDLE_DB_PRIORITY": "interactive",
    "ADAPTIVE_CANDLE_DB_TIMEOUT_SECONDS": "12",
    "DB_BACKGROUND_DROP_WHEN_BUSY": "0",
    "DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT": "0",
    "DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE": "0",
    "STAGING_QUALITY_GATES_ADVISORY": "1",
    "STAGING_DELIVERY_FRESHNESS_ADVISORY": "1",
    "STAGING_TEST_DELIVERY_LIVE_EXECUTION_BLOCK": "1",
    "DIAGNOSTIC_HEATMAP_EMPTY_CYCLES": "1",
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
    """Resolve the actual deployment environment consistently.

    Railway's environment identity is authoritative when present.  A stale
    application-level ``APP_ENV=production`` must not make a Railway staging
    deployment behave like production while the version banner correctly says
    staging.
    """
    return str(
        env.get("RAILWAY_ENVIRONMENT_NAME")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("APP_ENV")
        or env.get("ENVIRONMENT")
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

    # Railway values are normally unquoted, but copied dotenv values sometimes
    # include literal quote characters. Strip only one matching outer pair so
    # key-prefix detection and the downstream Paystack client see the real key.
    for key_name in ("PAYSTACK_SECRET_KEY", "PAYSTACK_PUBLIC_KEY"):
        raw_value = str(env.get(key_name) or "").strip()
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
            raw_value = raw_value[1:-1].strip()
        if raw_value:
            env[key_name] = raw_value

    environment = _environment_name(env)
    requested = _truthy(env.get("FULL_SYSTEM_STAGING_TEST_MODE"))
    ack_valid = is_full_system_ack_valid(env.get("FULL_SYSTEM_STAGING_TEST_ACK"))

    # Production never permits the staging integration mode, but report the
    # acknowledgement truthfully so diagnostics do not mislabel an environment
    # mismatch as an invalid token.
    if environment in {"production", "prod"}:
        # Production is public by default and must never inherit a Railway
        # staging allowlist or testing override from an earlier environment.
        forced_off: list[str] = []
        for name in (
            "PUBLIC_TESTING_MODE",
            "FULL_SYSTEM_STAGING_TEST_MODE",
            "FULL_SYSTEM_STAGING_TEST_ACTIVE",
            "STAGING_QUALITY_GATES_ADVISORY",
            "STAGING_DELIVERY_FRESHNESS_ADVISORY",
            "STAGING_TEST_DELIVERY_LIVE_EXECUTION_BLOCK",
            "FREE_RANDOM_DISTRIBUTION_ENABLED",
        ):
            if _truthy(env.get(name)):
                forced_off.append(name)
            env[name] = "0"
        if str(env.get("DELIVERY_AUDIENCE_ALLOWLIST") or "").strip():
            forced_off.append("DELIVERY_AUDIENCE_ALLOWLIST")
        if _truthy(env.get("RESEND_AUDIENCE_ALLOWLIST_ONLY")):
            forced_off.append("RESEND_AUDIENCE_ALLOWLIST_ONLY")
        env["DELIVERY_AUDIENCE_ALLOWLIST"] = ""
        env["RESEND_AUDIENCE_ALLOWLIST_ONLY"] = "0"
        env["PAYMENTS_PUBLIC_TEST_MODE"] = "0"

        # Live-money flags are admitted only when their complete production
        # dependency contract passes. Invalid partial activation is forced off
        # before any execution-bearing module imports configuration.
        from core.financial_activation import force_invalid_financial_flags_off

        financial_forced_off = force_invalid_financial_flags_off(env)
        env["FINANCIAL_ACTIVATION_FORCED_OFF"] = ",".join(financial_forced_off)
        forced_off.extend(name for name in financial_forced_off if name not in forced_off)
        return RuntimeSafetyResult(
            environment, False, ack_valid, (), tuple(forced_off), (), "",
        )

    enabled = bool(requested and ack_valid)
    forced_on: list[str] = []
    forced_off: list[str] = []
    boundaries: list[str] = []

    if enabled:
        for name in _FULL_SYSTEM_FLAGS:
            if not _truthy(env.get(name)):
                forced_on.append(name)
            env[name] = "1"

        env["FULL_SYSTEM_STAGING_TEST_ACTIVE"] = "1"

        for name, value in _NONPRODUCTION_HARD_BOUNDARIES.items():
            if str(env.get(name) or "").strip() != value:
                boundaries.append(name)
            env[name] = value

        for name, value in _FULL_SYSTEM_OPERATIONAL_SETTINGS.items():
            if str(env.get(name) or "").strip() != value:
                boundaries.append(name)
            env[name] = value

        # Paystack may be tested with normal test keys or, when explicitly
        # acknowledged, with guarded live keys for allowlisted users under a
        # transaction cap. Live mode never silently activates from key presence.
        paystack_key = _clean_paystack_key(env.get("PAYSTACK_SECRET_KEY"))
        paystack_public = _clean_paystack_key(env.get("PAYSTACK_PUBLIC_KEY"))
        live_requested = _truthy(env.get("PAYSTACK_LIVE_STAGING_ENABLED"))
        live_ack_valid = _normalise_ack(env.get("PAYSTACK_LIVE_STAGING_ACK")) == _PAYSTACK_LIVE_ACK
        live_key_pair = paystack_key.startswith("sk_live_") and paystack_public.startswith("pk_live_")
        test_users = str(
            env.get("PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS")
            or env.get("FULL_SYSTEM_TEST_USER_IDS")
            or env.get("DELIVERY_AUDIENCE_ALLOWLIST")
            or env.get("OWNER_TELEGRAM_ID")
            or env.get("TELEGRAM_OWNER_ID")
            or ""
        ).strip()
        live_staging_active = bool(live_requested and live_ack_valid and live_key_pair and test_users)
        env["PAYSTACK_LIVE_STAGING_ACTIVE"] = "1" if live_staging_active else "0"

        if live_staging_active:
            env["PAYMENTS_PUBLIC_TEST_MODE"] = "0"
            boundaries.append("PAYSTACK_LIVE_STAGING_GUARDED")
        else:
            env["PAYMENTS_PUBLIC_TEST_MODE"] = "1"
            if paystack_key.startswith("sk_live_"):
                boundaries.append("PAYSTACK_LIVE_KEY_REJECTED")
                for name in ("PAYMENTS_ENABLED", "PAYMENTS_PUBLIC_ENABLED", "REAL_PAYOUTS_ENABLED"):
                    if _truthy(env.get(name)):
                        forced_off.append(name)
                    env[name] = "0"
                if not live_requested:
                    boundaries.append("PAYSTACK_LIVE_STAGING_NOT_ENABLED")
                elif not live_ack_valid:
                    boundaries.append("PAYSTACK_LIVE_STAGING_ACK_INVALID")
                elif not live_key_pair:
                    boundaries.append("PAYSTACK_LIVE_KEY_PAIR_INVALID")
                elif not test_users:
                    boundaries.append("PAYSTACK_LIVE_STAGING_ALLOWLIST_MISSING")

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
        env["FULL_SYSTEM_STAGING_TEST_ACTIVE"] = "0"
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


__all__ = ["RuntimeSafetyResult", "FULL_SYSTEM_STAGING_TEST_ACK_VALUE", "PAYSTACK_LIVE_STAGING_ACK_VALUE", "apply_runtime_safety_environment", "is_full_system_ack_valid"]
