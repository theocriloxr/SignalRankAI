"""Operator Telegram menus keep every operator command within Telegram's 100-command limit (29 Oct 2026).

The owner can use 123 catalogue commands. The menu was cut at 100 in
catalogue order, which dropped the owner's own controls (kill_switch,
system_health, queue_status, release_status, ...) because they come last.
"""
from __future__ import annotations

from core.tier_policy import tier_rank
from signalrank_telegram import command_catalog as cc

CUSTOMER_TIERS = ("FREE", "PREMIUM", "VIP")
OPERATOR_TIERS = ("ADMIN", "OWNER")


def _eligible(tier: str) -> list[str]:
    return [s.name for s in cc.COMMANDS if tier_rank(s.tier) <= tier_rank(tier) and s.botfather]


def _menu(tier: str) -> list[str]:
    return [name for name, _ in cc.botfather_commands(tier)]


def test_every_menu_fits_telegrams_limit():
    for tier in CUSTOMER_TIERS + OPERATOR_TIERS:
        assert len(_menu(tier)) <= cc.MENU_LIMIT, tier


def test_operators_keep_every_operator_command():
    for tier in OPERATOR_TIERS:
        menu = set(_menu(tier))
        operator = {s.name for s in cc.COMMANDS if tier_rank(s.tier) >= tier_rank("ADMIN")
                    and tier_rank(s.tier) <= tier_rank(tier)}
        assert operator <= menu, (tier, sorted(operator - menu))
    owner = set(_menu("OWNER"))
    for name in ("kill_switch", "system_health", "queue_status", "release_status", "account_merges", "help", "status"):
        assert name in owner, name


def test_customer_menus_are_unchanged():
    for tier in CUSTOMER_TIERS:
        assert _menu(tier) == _eligible(tier), tier


def test_only_customer_commands_are_left_out_and_they_all_exist():
    names = {s.name: s for s in cc.COMMANDS}
    assert cc.OPERATOR_MENU_OMIT <= set(names), sorted(cc.OPERATOR_MENU_OMIT - set(names))
    assert all(tier_rank(names[n].tier) < tier_rank("ADMIN") for n in cc.OPERATOR_MENU_OMIT)
    left_out = set(_eligible("OWNER")) - set(_menu("OWNER"))
    assert left_out <= cc.OPERATOR_MENU_OMIT, sorted(left_out - cc.OPERATOR_MENU_OMIT)


def test_help_still_lists_every_command():
    from signalrank_telegram.commands import _help_page_definitions

    listed = {cmd.lstrip("/") for page in _help_page_definitions().values() for cmd, _ in page["commands"]}
    assert {s.name for s in cc.COMMANDS} <= listed
    assert len(cc.visible_commands("OWNER")) == len(cc.COMMANDS)  # only the menu is capped


def test_future_growth_still_prefers_operator_commands(monkeypatch):
    extra = tuple(cc.CommandSpec(f"customer_extra_{i}", "Synthetic", "FREE", "Test") for i in range(40))
    monkeypatch.setattr(cc, "COMMANDS", cc.COMMANDS + extra)
    menu = _menu("OWNER")
    assert len(menu) == cc.MENU_LIMIT
    operator = {s.name for s in cc.COMMANDS if tier_rank(s.tier) >= tier_rank("ADMIN")}
    assert operator <= set(menu)
