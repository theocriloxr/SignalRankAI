"""Telegram /watchlist and /journal on the same rows as the web workspace (CX-CHAN-01).

Both commands resolve the Telegram identity to the canonical account and call
the shared services in ``services.platform``, so a list or entry made in one
channel shows up in the other. They answer only in a private chat: a journal
is private and a group reply would expose it. Deleting a whole list or an
entry needs the word ``confirm``.
"""
from __future__ import annotations

import os
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from db.session import get_session
from signalrank_telegram.command_resilience import safe_command_error

WATCHLIST_HELP = (
    "👀 /watchlist — the same lists as your web workspace\n"
    "/watchlist — show your lists\n"
    "/watchlist add BTCUSDT [list name]\n"
    "/watchlist remove BTCUSDT [list name]\n"
    "/watchlist new <name>\n"
    "/watchlist delete <name> confirm\n"
    "Without a list name, your default list is used (created on first add)."
)
JOURNAL_HELP = (
    "📓 /journal — the same journal as your web workspace\n"
    "/journal — your latest entries\n"
    "/journal add <what happened, what you learned> #tags\n"
    "/journal delete <entry id> confirm\n"
    "Entries are private to your account."
)
PRIVATE_ONLY = "🔒 Use this in your private chat with the bot; it is not shown in groups."


def _web_url(path: str) -> str:
    base = str(os.getenv("APP_BASE_URL") or os.getenv("WEB_APP_URL") or "https://signalrank.criloxsolutions.com")
    return base.rstrip("/") + path


def _is_private(update: Update) -> bool:
    chat = getattr(update, "effective_chat", None)
    return str(getattr(chat, "type", "private") or "private") == "private"


async def _account(session: Any, update: Update) -> int:
    from services.platform.identity import ensure_telegram_user

    return await ensure_telegram_user(
        session,
        telegram_user_id=int(update.effective_user.id),
        username=getattr(update.effective_user, "username", None),
    )


def _strip_word(words: list[str], word: str) -> list[str]:
    return words[1:] if words and words[0].lower() == word else words


def format_watchlists(lists: list[dict[str, Any]], labels: dict[str, str]) -> str:
    if not lists:
        return "👀 You have no watchlists yet.\n\nStart one with /watchlist add BTCUSDT."
    lines = ["👀 Your watchlists"]
    for item in lists[:20]:
        ids = [str(entry.get("instrument_id")) for entry in (item.get("items") or []) if entry.get("instrument_id")]
        symbols = sorted(labels.get(i, i) for i in ids)
        marker = " (default)" if item.get("is_default") else ""
        shown = ", ".join(symbols[:30]) + (f" and {len(symbols) - 30} more" if len(symbols) > 30 else "")
        lines.append(f"\n• {item.get('name')}{marker} — {len(symbols)} instrument{'s' if len(symbols) != 1 else ''}")
        if symbols:
            lines.append("  " + shown)
    if len(lists) > 20:
        lines.append(f"\n…and {len(lists) - 20} more lists on the web.")
    lines.append(f"\nAlso on the web: {_web_url('/app/watchlists')}")
    return "\n".join(lines)


def format_candidates(query: str, candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return f"No active instrument matches “{query[:40]}”. Check the symbol with /liveprice or search on the web."
    lines = [f"“{query[:40]}” matches several instruments. Add one by its id:"]
    for row in candidates[:5]:
        lines.append(f"• {row.get('instrument_id')} — {row.get('display_symbol')} "
                     f"({row.get('asset_class')}, {row.get('instrument_type')})")
    return "\n".join(lines)


async def _target_list(session: Any, uid: int, name_words: list[str], *, create_default: bool) -> dict[str, Any] | None:
    """A named list, or the default one; only an add may create the default list."""
    from services.platform import watchlists

    if name_words:
        return await watchlists.find_watchlist(session, uid, " ".join(name_words))
    if create_default:
        return await watchlists.default_watchlist(session, uid)
    lists = await watchlists.list_watchlists(session, uid)
    return lists[0] if lists else None


async def watchlist_reply(session: Any, uid: int, args: list[str]) -> str:
    """Run one /watchlist request inside the caller's transaction and return the reply."""
    from services.platform import watchlists

    action = (args[0].lower() if args else "list")
    rest = list(args[1:])
    if action in {"list", "show"}:
        lists = await watchlists.list_watchlists(session, uid)
        ids = [str(e.get("instrument_id")) for w in lists for e in (w.get("items") or [])]
        return format_watchlists(lists, await watchlists.instrument_labels(session, ids))
    if action == "new":
        try:
            created = await watchlists.create_watchlist(session, uid, " ".join(rest))
        except watchlists.WatchlistError as exc:
            if str(exc) == "invalid_name":
                return "Give the list a name of up to 100 characters: /watchlist new <name>"
            return "You already have a list with that name."
        return f"✅ Created “{created['name']}”. Add to it with /watchlist add BTCUSDT {created['name']}"
    if action in {"add", "remove"}:
        if not rest:
            return f"Which instrument? /watchlist {action} BTCUSDT [list name]"
        name_words = _strip_word(rest[1:], "to" if action == "add" else "from")
        # Resolve the instrument first so a mistyped symbol never creates an empty default list.
        match, candidates = await watchlists.resolve_instrument(session, rest[0])
        if match is None:
            return format_candidates(rest[0], candidates)
        target = await _target_list(session, uid, name_words, create_default=(action == "add"))
        if target is None:
            if not name_words:
                return "You have no watchlists yet. See /watchlist."
            return (f"You have no list named “{' '.join(name_words)[:100]}”. "
                    "Create it with /watchlist new <name>, or see /watchlist.")
        label = str(match.get("display_symbol") or match["instrument_id"])
        if action == "add":
            added = await watchlists.add_item(session, uid, target["watchlist_id"], match["instrument_id"])
            return (f"✅ Added {label} to “{target['name']}”." if added
                    else f"{label} is already on “{target['name']}”.")
        removed = await watchlists.remove_item(session, uid, target["watchlist_id"], match["instrument_id"])
        return (f"✅ Removed {label} from “{target['name']}”." if removed
                else f"{label} is not on “{target['name']}”.")
    if action == "delete":
        confirmed = bool(rest) and rest[-1].lower() == "confirm"
        name_words = rest[:-1] if confirmed else rest
        target = await watchlists.find_watchlist(session, uid, " ".join(name_words)) if name_words else None
        if target is None:
            return "Name the list to delete: /watchlist delete <name> confirm"
        if not confirmed:
            return (f"This deletes “{target['name']}” and its instruments on the web too. "
                    f"Send /watchlist delete {target['name']} confirm to go ahead.")
        await watchlists.delete_watchlist(session, uid, target["watchlist_id"])
        return f"🗑 Deleted “{target['name']}”."
    return WATCHLIST_HELP


def _entry_line(entry: dict[str, Any]) -> str:
    when = str(entry.get("occurred_at") or "")[:16].replace("T", " ")
    summary = " ".join(str(entry.get("title") or entry.get("notes") or "(no text)").split())
    if len(summary) > 90:
        summary = summary[:89] + "…"
    extra = []
    if entry.get("result_r") is not None:
        extra.append(f"{float(entry['result_r']):+.2f}R")
    tags = entry.get("tags") or []
    if tags:
        extra.append(" ".join("#" + str(tag) for tag in list(tags)[:5]))
    tail = f" · {' · '.join(extra)}" if extra else ""
    return f"• {str(entry.get('journal_entry_id'))[:8]} · {when} UTC — {summary}{tail}"


def format_journal(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "📓 Your journal is empty.\n\nAdd an entry with /journal add <what happened> #tags"
    lines = ["📓 Latest journal entries"] + [_entry_line(entry) for entry in entries]
    lines.append(f"\nFull journal, with filters and trade links: {_web_url('/app/journal')}")
    return "\n".join(lines)


async def journal_reply(session: Any, uid: int, args: list[str]) -> str:
    """Run one /journal request inside the caller's transaction and return the reply."""
    from services.platform import journal

    action = (args[0].lower() if args else "list")
    rest = list(args[1:])
    if action in {"list", "show"}:
        return format_journal(await journal.list_entries(session, uid, limit=5))
    if action == "add":
        note, tags = journal.split_hashtags(" ".join(rest))
        if not note:
            return "Write the entry after add: /journal add Took the breakout too early #fomo"
        entry_id = await journal.create_entry(session, uid, notes=note, tags=tags)
        tag_text = f" Tags: {' '.join('#' + t for t in tags)}." if tags else ""
        return f"✅ Saved journal entry {entry_id[:8]}.{tag_text}"
    if action == "delete":
        confirmed = bool(rest) and rest[-1].lower() == "confirm"
        short_id = (rest[0] if rest else "").lower()
        matches = await journal.match_entries(session, uid, short_id)
        if not matches:
            return "No entry of yours starts with that id. /journal lists ids (use at least 6 characters)."
        if len(matches) > 1:
            return "That id matches more than one entry; use more characters."
        if not confirmed:
            return f"This deletes entry {matches[0][:8]} everywhere. Send /journal delete {short_id} confirm to go ahead."
        await journal.delete_entry(session, uid, matches[0])
        return f"🗑 Deleted journal entry {matches[0][:8]}."
    return JOURNAL_HELP


async def _run(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str, handler, failure: str) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not _is_private(update):
        await update.message.reply_text(PRIVATE_ONLY)
        return
    args = [str(arg) for arg in (context.args or [])]
    try:
        async with get_session(priority="interactive", label=label, timeout_seconds=10.0) as session:
            uid = await _account(session, update)
            reply = await handler(session, uid, args)
            await session.commit()
    except Exception as exc:
        await update.message.reply_text(safe_command_error(failure, exc))
        return
    await update.message.reply_text(reply, disable_web_page_preview=True)


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, context, "telegram.watchlist", watchlist_reply, "Could not update your watchlists.")


async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, context, "telegram.journal", journal_reply, "Could not open your journal.")


__all__ = [
    "JOURNAL_HELP", "WATCHLIST_HELP", "format_journal", "format_watchlists", "journal_command", "journal_reply",
    "watchlist_command", "watchlist_reply",
]
