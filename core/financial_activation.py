"""Fail-closed production activation policy for real-money capabilities.

This module centralises the dependency graph behind the environment flags that
cross an external money boundary.  It never turns a capability on.  Instead it
reports whether the requested combination is safe enough to admit and can force
invalid combinations back off during early runtime startup.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, MutableMapping

from core.env import env_bool

LIVE_FINANCIAL_ACK_VALUE = "I_ACCEPT_REAL_MONEY_TRADING_AND_PAYOUT_RISK"
REAL_PAYOUT_ACK_VALUE = "I_ACCEPT_MANUAL_APPROVAL_REAL_PAYOUT_RISK"
PAYSTACK_TRANSFERS_ACK_VALUE = "I_CONFIRM_PAYSTACK_TRANSFERS_IS_ENABLED_FOR_THIS_BUSINESS"
BYBIT_DEDICATED_ACCOUNT_ACK_VALUE = "I_CONFIRM_BYBIT_ACCOUNT_IS_DEDICATED_TO_SIGNALRANKAI"
PRODUCTION_EXECUTION_ACK_VALUE = "I_APPROVE_OWNER_ONLY_LIVE_EXECUTION"
MAX_ACTIVATION_WINDOW = timedelta(hours=24)


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


def _csv(value: str) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in str(value or "").split(",") if item.strip()}))


def _positive_number(value: str) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number > 0 and number < float("inf")


def _utc_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


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
    owner_id = _raw(environ, "LIVE_ACTIVATION_OWNER_TELEGRAM_ID")
    allowed_users = _csv(_raw(environ, "LIVE_EXECUTION_ALLOWED_TELEGRAM_USERS"))
    allowed_accounts = _csv(_raw(environ, "LIVE_EXECUTION_ALLOWED_BROKER_ACCOUNTS"))
    allowed_providers = {item.lower() for item in _csv(_raw(environ, "LIVE_EXECUTION_ALLOWED_PROVIDERS"))}
    allowed_symbols = _csv(_raw(environ, "LIVE_EXECUTION_ALLOWED_SYMBOLS"))
    started_at = _utc_timestamp(_raw(environ, "LIVE_ACTIVATION_STARTED_AT"))
    expires_at = _utc_timestamp(_raw(environ, "LIVE_ACTIVATION_EXPIRES_AT"))
    now = datetime.now(timezone.utc)
    activation_window_valid = bool(
        started_at
        and expires_at
        and started_at <= now < expires_at
        and expires_at - started_at <= MAX_ACTIVATION_WINDOW
    )
    integrity_certified = _bool(environ, "PRODUCTION_INTEGRITY_CERTIFIED")
    integrity_report_id = _raw(environ, "PRODUCTION_INTEGRITY_CERTIFICATION_ID")
    runtime_certification_id = _raw(environ, "LIVE_RUNTIME_CERTIFICATION_ID")
    calibration_artifact_id = _raw(environ, "ML_CALIBRATION_ARTIFACT_ID")
    copy_certification_id = _raw(environ, "COPY_TRADING_CERTIFICATION_ID")
    provider_discovery_certification_id = _raw(environ, "ASSET_DISCOVERY_CERTIFICATION_ID")
    freshness_certification_id = _raw(environ, "FRESHNESS_CERTIFICATION_ID")
    profile_routing_certification_id = _raw(environ, "PROFILE_ROUTING_CERTIFICATION_ID")
    paper_trading_certification_id = _raw(environ, "PAPER_TRADING_CERTIFICATION_ID")
    outcome_tracker_certification_id = _raw(environ, "OUTCOME_TRACKER_CERTIFICATION_ID")
    performance_truth_certification_id = _raw(environ, "PERFORMANCE_TRUTH_CERTIFICATION_ID")
    shadow_tracking_certification_id = _raw(environ, "SHADOW_TRACKING_CERTIFICATION_ID")
    engine_pulse_certification_id = _raw(environ, "ENGINE_PULSE_CERTIFICATION_ID")
    owner_scope_valid = bool(owner_id.isdigit() and allowed_users == (owner_id,))
    provider_scope_valid = bool(
        allowed_providers
        and allowed_providers.issubset({"mt5", "bybit"})
        and (not mt5_live or "mt5" in allowed_providers)
        and (not bybit_execution or "bybit" in allowed_providers)
    )

    checks: list[ActivationCheck] = [
        ActivationCheck("environment_production", environment in {"production", "prod"}, f"environment={environment}"),
        ActivationCheck("testing_disabled", not _bool(environ, "PUBLIC_TESTING_MODE") and not _bool(environ, "FULL_SYSTEM_STAGING_TEST_MODE"), "testing and staging modes must be off"),
        ActivationCheck("master_switch", (not requested) or master_enabled, "LIVE_FINANCIAL_FEATURES_ENABLED must be on for requested live-money features"),
        ActivationCheck("risk_acknowledgement", (not requested) or ack_valid, "exact live-financial acknowledgement required"),
        ActivationCheck("production_execution_acknowledgement", (not live_execution_requested) or _raw(environ, "PRODUCTION_EXECUTION_ACK") == PRODUCTION_EXECUTION_ACK_VALUE, "exact owner-only production execution acknowledgement required"),
        ActivationCheck("owner_identity_and_user_scope", (not live_execution_requested) or owner_scope_valid, "owner identity must be numeric and the live Telegram allowlist must contain only that owner"),
        ActivationCheck("broker_account_allowlist", (not live_execution_requested) or bool(allowed_accounts), "at least one exact broker account ID is required"),
        ActivationCheck("provider_allowlist", (not live_execution_requested) or provider_scope_valid, "provider allowlist must contain only enabled mt5/bybit adapters"),
        ActivationCheck("symbol_allowlist", (not live_execution_requested) or bool(allowed_symbols), "at least one exact live symbol is required"),
        ActivationCheck("demo_certification", (not live_execution_requested) or _configured(_raw(environ, "DEMO_CERTIFICATION_REPORT_ID")), "a completed demo certification report ID is required"),
        ActivationCheck("production_integrity_certification", (not live_execution_requested) or (integrity_certified and _configured(integrity_report_id)), "production-integrity certification and report ID are required"),
        ActivationCheck("live_runtime_certification", (not live_execution_requested) or _configured(runtime_certification_id), "a post-deploy live-runtime certification ID is required"),
        ActivationCheck("calibrated_model_artifact", (not live_execution_requested) or _configured(calibration_artifact_id), "live execution requires a persisted calibration artifact ID"),
        ActivationCheck("freshness_certification", (not live_execution_requested) or _configured(freshness_certification_id), "live execution requires post-deploy signal freshness certification"),
        ActivationCheck("profile_routing_certification", (not live_execution_requested) or _configured(profile_routing_certification_id), "live execution requires generation, delivery and execution profile-routing certification"),
        ActivationCheck("paper_trading_certification", (not live_execution_requested) or _configured(paper_trading_certification_id), "live execution requires a completed paper-trading integrity certification"),
        ActivationCheck("outcome_tracker_certification", (not live_execution_requested) or _configured(outcome_tracker_certification_id), "live execution requires TP/SL lifecycle and reconciliation certification"),
        ActivationCheck("performance_truth_certification", (not live_execution_requested) or _configured(performance_truth_certification_id), "live execution requires proof-backed performance-ledger certification"),
        ActivationCheck("shadow_tracking_certification", (not live_execution_requested) or _configured(shadow_tracking_certification_id), "live execution requires rejected-signal shadow tracking and false-negative certification"),
        ActivationCheck("engine_pulse_certification", (not live_execution_requested) or _configured(engine_pulse_certification_id), "live execution requires reconciled Engine Pulse counter certification"),
        ActivationCheck("copy_trading_certification", (not copy_trade) or _configured(copy_certification_id), "copy trading requires a dedicated certification ID"),
        ActivationCheck("provider_discovery_certification", (not live_execution_requested) or (_configured(provider_discovery_certification_id) and not _bool(environ, "ALLOW_STATIC_ASSET_FALLBACK")), "live execution requires provider-backed asset discovery with static fallback disabled"),
        ActivationCheck("maximum_live_position_size", (not live_execution_requested) or _positive_number(_raw(environ, "LIVE_MAX_POSITION_SIZE")), "a positive maximum live position size is required"),
        ActivationCheck("maximum_daily_loss", (not live_execution_requested) or _positive_number(_raw(environ, "LIVE_MAX_DAILY_LOSS")), "a positive maximum daily loss is required"),
        ActivationCheck("maximum_total_exposure", (not live_execution_requested) or _positive_number(_raw(environ, "LIVE_MAX_TOTAL_EXPOSURE")), "a positive maximum total exposure is required"),
        ActivationCheck("activation_window", (not live_execution_requested) or activation_window_valid, "activation timestamps must be UTC-aware, current, and no longer than 24 hours"),
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
    "PRODUCTION_EXECUTION_ACK_VALUE",
    "evaluate_financial_activation",
    "force_invalid_financial_flags_off",
]
