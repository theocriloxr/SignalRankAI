from __future__ import annotations

import re
from pathlib import Path

from signalrank_telegram.command_resilience import safe_command_error
from signalrank_telegram.ux_copy import (
    about_message,
    faq_message,
    help_page_message,
    pricing_message,
    safe_error_message,
    start_message,
    support_message,
    terms_accepted_message,
    upgrade_message,
    waitlist_joined_message,
)


ROOT = Path(__file__).resolve().parents[1]


def _public_copy() -> str:
    return "\n".join(
        (
            start_message(),
            about_message(),
            faq_message(),
            support_message(),
            terms_accepted_message(),
            waitlist_joined_message(),
            pricing_message(
                free_limit=3,
                premium_limit=12,
                vip_limit=25,
                premium_month_price=24000,
                premium_quarter_price=56000,
                premium_year_price=192000,
                vip_line="<b>VIP — capacity managed</b>",
            ),
            upgrade_message(
                premium_month_price=24000,
                premium_quarter_price=56000,
                premium_year_price=192000,
                vip_line="<b>VIP — capacity managed</b>",
            ),
        )
    )


def test_public_copy_is_capability_aware_and_never_tier_implies_execution() -> None:
    copy = _public_copy()
    lowered = copy.lower()

    for required in (
        "provider",
        "account",
        "risk",
        "execution",
        "educational",
        "no tier guarantees profit",
    ):
        assert required in lowered

    for stale in (
        "signalrankai does not execute trades",
        "unlimited automated executions",
        "mt5 auto-trading (vip)",
        "high-probability setups",
        "unlock analytics instantly",
    ):
        assert stale not in lowered

    assert "paid" in lowered or "plan" in lowered
    assert "nothing is enabled simply because a plan is paid" in lowered


def test_pricing_and_upgrade_copy_preserve_dynamic_commercial_values() -> None:
    pricing = pricing_message(
        free_limit=2,
        premium_limit=11,
        vip_limit=19,
        premium_month_price=25001,
        premium_quarter_price=57002,
        premium_year_price=193003,
        vip_line="<b>VIP — 7 seats left</b>",
    )
    upgrade = upgrade_message(
        premium_month_price=25001,
        premium_quarter_price=57002,
        premium_year_price=193003,
        vip_line="<b>VIP — 7 seats left</b>",
    )

    for value in ("₦25,001", "₦57,002", "₦193,003"):
        assert value in pricing
        assert value in upgrade
    for value in ("2", "11", "19"):
        assert value in pricing
    assert "7 seats left" in pricing
    assert "7 seats left" in upgrade
    assert "hard risk" in pricing.lower()
    assert "fail-closed" in upgrade.lower()


def test_help_page_preview_is_explicit_without_promising_unlock() -> None:
    text = help_page_message(
        title="⭐ Premium commands",
        page=2,
        last_page=3,
        tier="FREE",
        required_tier="PREMIUM",
        commands=(("/performance", "Tracked performance"),),
        locked=True,
        footer="Premium expands analytics access.",
    )
    assert "Preview · requires Premium" in text
    assert "🔒 /performance" in text
    assert "Use the page buttons below or /support" in text


def test_waitlist_and_support_copy_never_make_payment_or_response_time_promises() -> None:
    waitlist = waitlist_joined_message().lower()
    support = support_message().lower()
    assert "24 hours" not in waitlist
    assert "personal payment link" not in waitlist
    assert "supported account flow" in waitlist
    for secret_word in ("password", "api key", "otp", "card"):
        assert secret_word in support or secret_word in waitlist


def test_safe_error_copy_keeps_reference_and_never_echoes_exception_secret() -> None:
    secret = "postgresql://user:password@example.invalid/db"
    result = safe_command_error("Could not load data", RuntimeError(secret))
    assert secret not in result
    assert re.search(r"Reference: CMD-[A-F0-9]{8}", result)
    assert "/support" in result
    assert "Do not send passwords" in result

    direct = safe_error_message(
        action="Could not continue",
        guidance="Please retry.",
        reference="CMD-ABCDEF12",
    )
    assert "Reference: CMD-ABCDEF12" in direct
    assert direct.startswith("❌ ")


def test_runtime_handlers_use_canonical_copy_and_remove_stale_plan_claims() -> None:
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    users = (ROOT / "signalrank_telegram" / "user_commands.py").read_text(encoding="utf-8")
    resilience = (ROOT / "signalrank_telegram" / "command_resilience.py").read_text(encoding="utf-8")

    for marker in (
        "pricing_message(",
        "upgrade_message(",
        "help_page_message(",
        "terms_accepted_message()",
        "waitlist_joined_message()",
        "msg = start_message()",
    ):
        assert marker in commands

    assert "msg = start_message()" in users
    assert "about_message()" in users
    assert "faq_message()" in users
    assert "support_message()" in users
    assert "safe_error_message(" in resilience

    tiers = commands[
        commands.index("async def tiers_command"):
        commands.index("# /mystats"),
    ]
    assert "_compose_pricing_message" in tiers
    assert "automated MT5 executions/day" not in tiers
    assert "Unlimited" not in tiers

    combined = commands + "\n" + users
    for stale in (
        "SignalRankAI does not execute trades",
        "Unlimited automated executions",
        "MT5 Auto‑Trading (VIP)",
        "high-probability setups",
        "unlock analytics instantly",
    ):
        assert stale not in combined
