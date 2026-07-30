"""Fail-closed production activation policy for real-money capabilities.

This module centralises the dependency graph behind the environment flags that
cross an external money boundary.  It never turns a capability on.  Instead it
reports whether the requested combination is safe enough to admit and can force
invalid combinations back off during early runtime startup.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, MutableMapping

from core.env import env_bool

LIVE_FINANCIAL_ACK_VALUE = "I_ACCEPT_REAL_MONEY_TRADING_AND_PAYOUT_RISK"
REAL_PAYOUT_ACK_VALUE = "I_ACCEPT_MANUAL_APPROVAL_REAL_PAYOUT_RISK"
PAYSTACK_TRANSFERS_ACK_VALUE = "I_CONFIRM_PAYSTACK_TRANSFERS_IS_ENABLED_FOR_THIS_BUSINESS"
BYBIT_DEDICATED_ACCOUNT_ACK_VALUE = "I_CONFIRM_BYBIT_ACCOUNT_IS_DEDICATED_TO_SIGNALRANKAI"


@dataclass(frozen=True, slots=True)
class ActivationCheck:
    name: str
    ok: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class FinancialActivationReport:
    requested: bool
    live_execution_requested: bool
    payouts_requested: bool
    ok: bool
    checks: tuple[ActivationCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "live_execution_requested": self.live_execution_requested,
            "payouts_requested": self.payouts_requested,
            "ok": self.ok,
            "checks": [asdict(check) for check in self.checks],
        }


def _raw(env: MutableMapping[str, str] | None, name: str) -> str:
    source = env if env is not None else os.environ
    return str(source.get(name) or "").strip().strip('"').strip("'")


def _bool(env: MutableMapping[str, str] | None, name: str, default: bool = False) -> bool:
    if env is None:
        return env_bool(name, default)
    value = _raw(env, name).lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disabled", ""}:
        return False
    return bool(default)


def _configured(value: str) -> bool:
    value = str(value or "").strip()
    if not value or (value.startswith("<") and value.endswith(">")):
        return False
    return value.lower() not in {"changeme", "change-me", "replace-me", "placeholder", "todo", "none", "null"}


def _environment(env: MutableMapping[str, str] | None) -> str:
    return (
        _raw(env, "RAILWAY_ENVIRONMENT_NAME")
        or _raw(env, "RAILWAY_ENVIRONMENT")
        or _raw(env, "APP_ENV")
        or _raw(env, "ENVIRONMENT")
        or "dev"
    ).lower()


def evaluate_financial_activation(
    environ: MutableMapping[str, str] | None = None,
) -> FinancialActivationReport:
    real_execution = _bool(environ, "REAL_EXECUTION_ENABLED")
    auto_execution = _bool(environ, "AUTO_EXECUTION_ENABLED")
    auto_trade = _bool(environ, "AUTO_TRADE_ENABLED")
    copy_trade = _bool(environ, "COPY_TRADE_ENABLED")
    mt5_live = _bool(environ, "MT5_ALLOW_LIVE_ACCOUNTS")
    bybit_execution = _bool(environ, "BYBIT_EXECUTION_ENABLED")
    payouts = _bool(environ, "REAL_PAYOUTS_ENABLED")
    requested = any((real_execution, auto_execution, auto_trade, copy_trade, mt5_live, bybit_execution, payouts))
    live_execution_requested = any((real_execution, auto_execution, auto_trade, copy_trade, mt5_live, bybit_execution))

    environment = _environment(environ)
    master_enabled = _bool(environ, "LIVE_FINANCIAL_FEATURES_ENABLED")
    ack_valid = _raw(environ, "LIVE_FINANCIAL_FEATURES_ACK") == LIVE_FINANCIAL_ACK_VALUE
    payout_ack_valid = _raw(environ, "REAL_PAYOUTS_ACK") == REAL_PAYOUT_ACK_VALUE
    transfer_ack_valid = _raw(environ, "PAYSTACK_TRANSFERS_APPROVED_ACK") == PAYSTACK_TRANSFERS_ACK_VALUE
    bybit_dedicated_ack_valid = _raw(environ, "BYBIT_DEDICATED_ACCOUNT_ACK") == BYBIT_DEDICATED_ACCOUNT_ACK_VALUE
    encryption_key = _raw(environ, "ENCRYPTION_KEY")
    metaapi_token = _raw(environ, "META_API_TOKEN")
    paystack_secret = _raw(environ, "PAYSTACK_SECRET_KEY")
    paystack_public = _raw(environ, "PAYSTACK_PUBLIC_KEY")

    checks: list[ActivationCheck] = [
        ActivationCheck("environment_production", environment in {"production", "prod"}, f"environment={environment}"),
        ActivationCheck("testing_disabled", not _bool(environ, "PUBLIC_TESTING_MODE") and not _bool(environ, "FULL_SYSTEM_STAGING_TEST_MODE"), "testing and staging modes must be off"),
        ActivationCheck("master_switch", (not requested) or master_enabled, "LIVE_FINANCIAL_FEATURES_ENABLED must be on for requested live-money features"),
        ActivationCheck("risk_acknowledgement", (not requested) or ack_valid, "exact live-financial acknowledgement required"),
        ActivationCheck("encryption_configured", (not live_execution_requested) or _configured(encryption_key), "ENCRYPTION_KEY is required for broker credentials"),
        ActivationCheck("global_kill_switch_clear", (not live_execution_requested) or not _bool(environ, "GLOBAL_EXECUTION_KILL_SWITCH", True), "GLOBAL_EXECUTION_KILL_SWITCH must be 0"),
        ActivationCheck("auto_execution_dependency", (not (auto_trade or copy_trade)) or auto_execution, "AUTO_TRADE/COPY_TRADE require AUTO_EXECUTION_ENABLED"),
        ActivationCheck("real_execution_dependency", (not (auto_execution or auto_trade or copy_trade or mt5_live or bybit_execution)) or real_execution, "all broker automation requires REAL_EXECUTION_ENABLED"),
        ActivationCheck("mt5_token", (not mt5_live) or _configured(metaapi_token), "META_API_TOKEN required for live MT5"),
        ActivationCheck("live_broker_available", (not live_execution_requested) or mt5_live or bybit_execution, "enable at least one live broker adapter"),
        ActivationCheck("bybit_mainnet", (not bybit_execution) or not _bool(environ, "BYBIT_TESTNET", True), "BYBIT_TESTNET must be 0 for live Bybit"),
        ActivationCheck("bybit_ip_binding", (not bybit_execution) or _bool(environ, "BYBIT_REQUIRE_IP_BINDING", True), "live Bybit keys must require IP binding"),
        ActivationCheck("bybit_dedicated_account", (not bybit_execution) or bybit_dedicated_ack_valid, "live Bybit requires a dedicated account with no manual or external trading"),
        ActivationCheck("bybit_reconciliation", (not bybit_execution) or _bool(environ, "BYBIT_RECONCILIATION_ENABLED", False), "Bybit reconciliation worker must be enabled"),
        ActivationCheck("payout_manual_approval", (not payouts) or _bool(environ, "PAYOUT_MANUAL_APPROVAL_REQUIRED", True), "real payouts require manual approval"),
        ActivationCheck("payout_acknowledgement", (not payouts) or payout_ack_valid, "exact payout acknowledgement required"),
        ActivationCheck("payout_payment_dependency", (not payouts) or (_bool(environ, "PAYMENTS_ENABLED") and _bool(environ, "PAYMENTS_PUBLIC_ENABLED")), "real payouts require public payments enabled"),
        ActivationCheck("paystack_transfers_approved", (not payouts) or _bool(environ, "PAYSTACK_TRANSFERS_ENABLED", False), "Paystack Transfers must be approved and enabled on the business account"),
        ActivationCheck("paystack_transfers_acknowledged", (not payouts) or transfer_ack_valid, "exact Paystack Transfers approval acknowledgement required"),
        ActivationCheck("paystack_transfer_otp_flow", (not payouts) or _bool(environ, "PAYSTACK_TRANSFER_OTP_FLOW_ENABLED", False), "Paystack transfer OTP finalization route must be enabled"),
        ActivationCheck("paystack_live_secret", (not payouts) or paystack_secret.startswith("sk_live_"), "real payouts require sk_live_ Paystack secret"),
        ActivationCheck("paystack_live_public", (not payouts) or paystack_public.startswith("pk_live_"), "real payouts require pk_live_ Paystack public key"),
        ActivationCheck("automatic_payouts_disabled", not _bool(environ, "AUTOMATIC_PAYOUTS_ENABLED", False), "automatic payouts are unsupported; owner approval is mandatory"),
    ]
    ok = (not requested) or all(check.ok for check in checks if check.blocking)
    return FinancialActivationReport(requested, live_execution_requested, payouts, ok, tuple(checks))


def force_invalid_financial_flags_off(
    environ: MutableMapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Force requested live-money features off unless the full contract passes."""
    env = environ if environ is not None else os.environ
    report = evaluate_financial_activation(env)
    if report.ok:
        return ()
    forced: list[str] = []
    for name in (
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "MT5_ALLOW_LIVE_ACCOUNTS",
        "BYBIT_EXECUTION_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "AUTOMATIC_PAYOUTS_ENABLED",
    ):
        if _bool(env, name):
            forced.append(name)
        env[name] = "0"
    return tuple(forced)


__all__ = [
    "ActivationCheck",
    "BYBIT_DEDICATED_ACCOUNT_ACK_VALUE",
    "FinancialActivationReport",
    "LIVE_FINANCIAL_ACK_VALUE",
    "REAL_PAYOUT_ACK_VALUE",
    "PAYSTACK_TRANSFERS_ACK_VALUE",
    "evaluate_financial_activation",
    "force_invalid_financial_flags_off",
]
