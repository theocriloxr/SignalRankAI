"""Canonical premium user-facing copy for SignalRank Telegram surfaces.

Keep capability claims conservative and durable. Execution, automation, broker
features and payments are described as eligibility-gated workflows rather than
unconditional promises. Pure functions make copy auditable and snapshot-testable.
"""
from __future__ import annotations

from collections.abc import Iterable


SUPPORT_HANDLE = "@theocrilox"
SUPPORT_URL = "https://t.me/theocrilox"


def rate_limit_message() -> str:
    return (
        "⏳ Too many requests in a short period. "
        "Please wait a moment and try again."
    )


def start_message() -> str:
    return (
        "👋 Welcome to SignalRankAI\n\n"
        "SignalRankAI is a risk-aware market intelligence and trading workflow "
        "platform for educational use. It ranks trade setups, tracks outcomes, "
        "and helps you manage a consistent process across crypto, FX, equities, "
        "indices, and commodities.\n\n"
        "What you can do here:\n"
        "• Review ranked trade setups with Entry, Stop and target context\n"
        "• Track outcomes and performance evidence instead of headline claims\n"
        "• Use paper trading and supported account workflows where eligible\n"
        "• Configure profiles, risk preferences, alerts, and broker connections\n\n"
        "Execution features are separately gated by your account, provider, "
        "permissions, reconciliation state, and hard risk policy. Nothing is "
        "enabled simply because a plan is paid.\n\n"
        "Start with /signals, review /proof, compare /pricing, or open /help."
    )


def about_message() -> str:
    return (
        "📊 About SignalRankAI\n\n"
        "SignalRankAI turns live market data, multiple strategy families, "
        "deterministic risk gates, ML-assisted ranking, and tracked outcomes into "
        "one auditable decision workflow.\n\n"
        "Coverage includes:\n"
        "• Crypto\n"
        "• Foreign exchange\n"
        "• Equities\n"
        "• Indices\n"
        "• Commodities\n\n"
        "The system can support paper, demo, manual-confirmed, assisted, and "
        "approved automated account workflows, but availability depends on the "
        "specific provider, account policy, permissions, reconciliation state, "
        "and release safety gates.\n\n"
        "No signal or model guarantees profit. Trading involves loss risk, and "
        "you remain responsible for every real-money decision.\n\n"
        f"Support: {SUPPORT_HANDLE}"
    )


def faq_message() -> str:
    return (
        "❔ SignalRankAI FAQ\n\n"
        "1) Does SignalRankAI place trades for me?\n"
        "Supported accounts can use paper, demo, manual-confirmed, assisted, or "
        "approved automated workflows. Real execution is never enabled by default "
        "and must pass account, provider, permission, reconciliation, and risk gates.\n\n"
        "2) Are profits guaranteed?\n"
        "No. Signal quality is filtered and measured, but every market system can "
        "lose. Past results do not guarantee future results.\n\n"
        "3) Why are there days with few or no signals?\n"
        "The engine is designed to reject weak, stale, closed-market, or "
        "risk-inappropriate setups rather than manufacture volume.\n\n"
        "4) Which markets are covered?\n"
        "Crypto, FX, equities, indices, and commodities. Availability can vary by "
        "market hours and provider support.\n\n"
        "5) What changes between Free, Premium, and VIP?\n"
        "Higher tiers expand timeliness, context, analytics, limits, profile "
        "controls, support, and eligibility for advanced workflows. Safety and "
        "hard risk checks are never bypassed by tier.\n\n"
        "6) Do subscriptions renew automatically?\n"
        "Only where an explicit supported billing flow says so and you opt in. "
        "Your account page is the source of truth for entitlement and expiry.\n\n"
        "7) Is this financial advice?\n"
        "No. SignalRankAI provides educational market intelligence and workflow tools."
    )


def support_message() -> str:
    return (
        "🎧 SignalRankAI Support\n\n"
        f"Contact {SUPPORT_HANDLE} for account, billing, access, delivery, or "
        "broker-connection help.\n\n"
        "For faster support, include the affected command or feature and any safe "
        "reference code shown by the bot. Never send passwords, card details, API "
        "keys, broker secrets, private keys, OTPs, or recovery codes."
    )


def main_menu_message() -> str:
    return (
        "🏠 SignalRankAI\n"
        "Choose what you want to do next. Your account permissions and safety "
        "policy determine which actions are available."
    )


def support_menu_message() -> str:
    return (
        "🎧 Support\n\n"
        "Choose support when you need help with billing, subscriptions, account "
        "access, signal delivery, broker connections, or an error reference.\n\n"
        f"Direct support: {SUPPORT_HANDLE}\n"
        "Useful commands: /faq · /policy · /refunds\n\n"
        "Never send credentials, OTPs, private keys, API secrets, or card details."
    )


def pricing_message(
    *,
    free_limit: int,
    premium_limit: int,
    vip_limit: int,
    premium_month_price: int,
    premium_quarter_price: int,
    premium_year_price: int,
    vip_line: str,
) -> str:
    return (
        "<b>SignalRankAI Plans</b>\n\n"
        "<b>Free</b>\n"
        f"• Up to {free_limit} signal deliveries/day under the active policy\n"
        "• Proof-oriented access with limited/delayed detail\n"
        "• Paper and educational workflow access where available\n\n"
        f"<b>Premium — ₦{premium_month_price:,}/month · "
        f"₦{premium_quarter_price:,}/quarter · ₦{premium_year_price:,}/year</b>\n"
        f"• Up to {premium_limit} signal deliveries/day under the active policy\n"
        "• Real-time signal context, Entry/Stop/targets, outcomes and analytics\n"
        "• Broader multi-asset visibility and profile controls\n"
        "• Connected-account tools where the provider/account is eligible\n\n"
        f"{vip_line}\n"
        f"• Up to {vip_limit} signal deliveries/day under the active policy\n"
        "• Priority workflow, stricter profile controls, deeper analytics, and "
        "expanded eligibility for advanced execution tooling\n"
        "• Webhook/API and broker controls remain subject to account policy and "
        "independent execution safety gates\n\n"
        "<i>Plans change workflow, limits and access—not market risk. No tier "
        "guarantees profit or bypasses hard risk controls.</i>"
    )


def upgrade_message(
    *,
    premium_month_price: int,
    premium_quarter_price: int,
    premium_year_price: int,
    vip_line: str,
) -> str:
    return (
        "<b>Upgrade SignalRankAI</b>\n\n"
        "Upgrade when you need more timely signals, deeper context, broader "
        "analytics, higher limits, profile controls, and access to advanced "
        "workflows—not because you expect guaranteed returns.\n\n"
        f"<b>Premium — ₦{premium_month_price:,}/month · "
        f"₦{premium_quarter_price:,}/quarter · ₦{premium_year_price:,}/year</b>\n"
        "• Real-time signal context and tracked outcomes\n"
        "• Full Entry / Stop / target detail\n"
        "• Performance, portfolio and profile workflows\n"
        "• Broader multi-asset coverage\n\n"
        f"{vip_line}\n"
        "• Priority workflow and stricter profile controls\n"
        "• Advanced risk/account tooling and expanded automation eligibility\n"
        "• Webhook/API and broker controls where independently supported\n\n"
        "Execution remains account-specific and fail-closed: provider support, "
        "permissions, reconciliation, hard risk limits and owner release gates "
        "still apply.\n\n"
        "<i>Educational market intelligence only. Trading involves loss risk.</i>\n\n"
        "Choose a plan below to continue to the supported checkout flow."
    )


def terms_accepted_message() -> str:
    return (
        "✅ <b>You're set up.</b>\n\n"
        "You can now explore ranked signals, outcome evidence, paper workflows, "
        "and account tools available to your tier.\n\n"
        "Try /signals for current setups, /proof for tracked evidence, /profile "
        "for trading preferences, or /pricing for plan details.\n\n"
        "Any execution feature remains separately permissioned and risk-gated."
    )


def waitlist_joined_message() -> str:
    return (
        "✅ You're on the VIP waitlist.\n\n"
        "We'll notify you through SignalRankAI when capacity is available. "
        "Only use payment links generated through the supported account flow, "
        "and never send card or banking credentials in chat."
    )


def help_page_message(
    *,
    title: str,
    page: int,
    last_page: int,
    tier: str,
    required_tier: str,
    commands: Iterable[tuple[str, str]],
    locked: bool,
    footer: str,
) -> str:
    state = (
        f"Preview · requires {required_tier.title()}"
        if locked and required_tier.upper() in {"PREMIUM", "VIP"}
        else f"Available for {tier.upper()}"
    )
    lines = [
        f"{title} · {page}/{last_page}",
        state,
        "",
    ]
    for command, description in commands:
        prefix = "🔒 " if locked and required_tier.upper() in {"PREMIUM", "VIP"} else "• "
        lines.append(f"{prefix}{command} — {description}")
    if footer:
        lines.extend(["", footer])
    lines.extend(["", "Use the page buttons below or /support if you need help."])
    return "\n".join(lines)


def safe_error_message(*, action: str, guidance: str, reference: str) -> str:
    action_text = str(action or "The request could not be completed.").strip()
    if not action_text.endswith((".", "!", "?")):
        action_text += "."
    return (
        f"❌ {action_text}\n"
        f"{str(guidance or '').strip()}\n"
        f"Reference: {reference}\n\n"
        "If this keeps happening, send the reference to /support. "
        "Do not send passwords, API keys, broker credentials, OTPs, or card details."
    )


__all__ = [
    "SUPPORT_HANDLE",
    "SUPPORT_URL",
    "about_message",
    "faq_message",
    "help_page_message",
    "main_menu_message",
    "pricing_message",
    "rate_limit_message",
    "safe_error_message",
    "start_message",
    "support_menu_message",
    "support_message",
    "terms_accepted_message",
    "upgrade_message",
    "waitlist_joined_message",
]
