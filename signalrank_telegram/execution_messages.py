"""User-safe execution readiness and failure messages.

Internal broker/preflight reason codes remain available in logs but are never
shown as the primary Telegram response.
"""
from __future__ import annotations

import html
from typing import Any


_REASON_MESSAGES = {
    "broker_account_not_ready": (
        "Your broker account is not connected and verified. Use /mt5_link to "
        "connect it, then run /mt5_status to complete the execution preflight."
    ),
    "user_execution_not_enabled": (
        "Trade execution is disabled for your account. Open /execution and "
        "enable it only after reviewing the consent and risk controls."
    ),
    "user_consent_required": (
        "Execution consent is still required. Open /execution, review the "
        "terms, and confirm before placing a broker order."
    ),
    "encrypted_credentials_required": (
        "Secure broker credentials are missing or invalid. Reconnect the "
        "account with /mt5_link and verify it with /mt5_status."
    ),
    "auto_execution_limit_disabled": (
        "Your execution risk limit is not configured. Set the allowed risk "
        "and daily-loss limits in /execution before enabling automatic orders."
    ),
    "auto_trade_disabled": (
        "Automatic broker execution is off. The signal is still available for "
        "monitoring and paper trading."
    ),
    "real_execution_disabled": (
        "Live broker execution is currently disabled by the platform safety "
        "gate. No order was placed."
    ),
    "mt5_allow_live_accounts_disabled": (
        "Live MT5 accounts are not enabled for this deployment. Connect a demo "
        "account or continue with paper trading."
    ),
    "tier_not_eligible": (
        "Your current plan does not include broker execution. View /tiers for "
        "the available execution features."
    ),
    "market_closed": "The market is currently closed, so no broker order was placed.",
    "signal_not_found": "The signal could not be verified, so no broker order was placed.",
    "signal_not_delivered": "This signal was not confirmed as delivered to your account.",
    "stale_signal": "The signal is no longer fresh enough for safe execution.",
}


def normalize_execution_reason(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    for key in _REASON_MESSAGES:
        if key in text:
            return key
    return text[:120] or "unknown"


def friendly_execution_reason(value: Any) -> str:
    key = normalize_execution_reason(value)
    return _REASON_MESSAGES.get(
        key,
        "The broker or execution preflight could not complete this request. "
        "No trade was opened. Run /mt5_status for the current readiness checks.",
    )


def execution_failure_html(value: Any, *, asset: str = "", mode: str = "") -> str:
    key = normalize_execution_reason(value)
    title = "Automatic trade not executed" if str(mode).lower() == "auto" else "Trade not executed"
    asset_line = f"Asset: <b>{html.escape(str(asset))}</b>\n" if asset else ""
    return (
        f"❌ <b>{title}</b>\n\n"
        f"{asset_line}{html.escape(friendly_execution_reason(key))}\n\n"
        f"Readiness reference: <code>{html.escape(key)}</code>"
    )


__all__ = [
    "execution_failure_html",
    "friendly_execution_reason",
    "normalize_execution_reason",
]
