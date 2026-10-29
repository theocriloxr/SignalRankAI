"""Account and operator commands never answer in a group chat (29 Oct 2026 threat model)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from signalrank_telegram.chat_scope import GROUP_SAFE_COMMANDS, PRIVATE_ONLY_REPLY, allowed_in_this_chat


def _update(chat_type: str | None):
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id=42, username="tester"),
        effective_chat=None if chat_type is None else SimpleNamespace(type=chat_type),
    )


def test_only_public_information_commands_may_answer_in_groups():
    from core.tier_policy import COMMAND_MINIMUM_TIER
    from signalrank_telegram.command_catalog import COMMANDS

    for name in GROUP_SAFE_COMMANDS:
        assert COMMAND_MINIMUM_TIER[name].value == "FREE", name
    for spec in COMMANDS:
        for chat in ("group", "supergroup", "channel"):
            expected = spec.name in GROUP_SAFE_COMMANDS
            assert allowed_in_this_chat(spec.name, _update(chat)) is expected, (spec.name, chat)
        assert allowed_in_this_chat(spec.name, _update("private"))
        assert allowed_in_this_chat(spec.name, _update(None))  # no chat: internal call
    for personal in ("status", "account", "paper_balance", "portfolio", "devices", "journal", "kill_switch", "start"):
        assert personal not in GROUP_SAFE_COMMANDS


@pytest.mark.asyncio
async def test_the_command_wrapper_refuses_in_a_group_before_doing_anything():
    from signalrank_telegram import bot

    handler = AsyncMock()
    wrapped = bot._audit_handler("status", handler)
    update = _update("supergroup")
    await wrapped(update, SimpleNamespace(args=[]))
    handler.assert_not_awaited()
    update.message.reply_text.assert_awaited_once_with(PRIVATE_ONLY_REPLY)


@pytest.mark.asyncio
async def test_start_is_also_private_only():
    from signalrank_telegram import bot

    handler = AsyncMock()
    update = _update("group")
    await bot._audit_handler("start", handler)(update, SimpleNamespace(args=[]))
    handler.assert_not_awaited()
    update.message.reply_text.assert_awaited_once_with(PRIVATE_ONLY_REPLY)
