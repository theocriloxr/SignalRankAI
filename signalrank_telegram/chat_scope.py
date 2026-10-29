"""Account commands answer only in private chats (29 Oct 2026 threat model).

Commands reply in the chat they were sent from. In a group, /status, /account,
/paper_balance, /portfolio, /devices or an owner command would show one
person's account or operations data to everyone in it. Only commands that show
public information may answer in a group; the rest ask for a private chat.
A missing chat (tests, internal calls) counts as private.
"""
from __future__ import annotations

from typing import Any

GROUP_SAFE_COMMANDS = frozenset(
    {"about", "pricing", "tiers", "market", "liveprice", "proof", "faq", "disclaimer"}
)
PRIVATE_ONLY_REPLY = (
    "🔒 This command answers only in your private chat with the bot, so your account "
    "details are never shown to a group. Open a private chat with the bot and send it there."
)


def is_private_chat(update: Any) -> bool:
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return True
    return str(getattr(chat, "type", "private") or "private") == "private"


def allowed_in_this_chat(command_name: str, update: Any) -> bool:
    return is_private_chat(update) or str(command_name or "").lower() in GROUP_SAFE_COMMANDS


__all__ = ["GROUP_SAFE_COMMANDS", "PRIVATE_ONLY_REPLY", "allowed_in_this_chat", "is_private_chat"]
