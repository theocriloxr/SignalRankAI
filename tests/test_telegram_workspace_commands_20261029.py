"""Telegram /watchlist and /journal share the web workspace's rows (29 Oct 2026).

Bot users had no watchlist or journal at all, and anything added on the web
was invisible in Telegram. These tests drive the real bot handlers and the
real web endpoint functions against the same PostgreSQL schema. They skip
without an isolated local PostgreSQL and fail when
SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import os
import random
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

from signalrank_telegram import workspace_commands as wc

@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


class _Message:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, value: str, **_kwargs) -> None:
        self.replies.append(value)


def _update(telegram_id: int, chat_type: str = "private"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_id, username=None),
        effective_chat=SimpleNamespace(type=chat_type),
        message=_Message(),
    )


async def _say(command, telegram_id: int, *args: str, chat_type: str = "private") -> str:
    update = _update(telegram_id, chat_type)
    await command(update, SimpleNamespace(args=list(args)))
    assert len(update.message.replies) == 1, update.message.replies
    return update.message.replies[0]


async def _linked_user() -> tuple[int, int]:
    """A web account that has linked its Telegram identity."""
    from db.session import get_session

    tag = uuid4().hex[:10]
    telegram_id = random.randint(3 * 10**9, 4 * 10**9)
    async with get_session() as session:
        uid = (await session.execute(text(
            "INSERT INTO users(username, telegram_user_id, created_at, tier, primary_email, auto_renew) "
            "VALUES(:u, :tg, NOW(), 'free', :e, FALSE) RETURNING id"
        ), {"u": f"ws-{tag}", "tg": telegram_id, "e": f"ws-{tag}@example.test"})).scalar_one()
        await session.commit()
    return uid, telegram_id


async def _instrument(symbol: str, instrument_type: str = "spot", *, active: bool = True) -> str:
    from db.session import get_session

    instrument_id = f"test:{instrument_type}:{symbol}:{uuid4().hex[:6]}"
    async with get_session() as session:
        await session.execute(text(
            "INSERT INTO instruments(instrument_id,canonical_symbol,display_symbol,asset_class,instrument_type,active,tradable) "
            "VALUES(:iid,:sym,:sym,'crypto',:itype,:active,TRUE)"
        ), {"iid": instrument_id, "sym": symbol, "itype": instrument_type, "active": active})
        await session.commit()
    return instrument_id


async def _web_watchlists(uid: int) -> list[dict]:
    from web.platform_api import list_watchlists

    return (await list_watchlists(user={"id": uid}))["watchlists"]


@pytest.mark.asyncio
async def test_a_list_made_in_telegram_is_the_web_list_and_back(isolated_postgres):
    from web.platform_api import WatchlistCreateRequest, WatchlistItemRequest, add_watchlist_item, create_watchlist

    uid, tg = await _linked_user()
    symbol = "WS" + uuid4().hex[:6].upper()
    btc = await _instrument(symbol)

    reply = await _say(wc.watchlist_command, tg, "add", symbol.lower())
    assert f"Added {symbol} to “My watchlist”" in reply
    web = await _web_watchlists(uid)
    assert [w["name"] for w in web] == ["My watchlist"] and web[0]["is_default"] is True
    assert [item["instrument_id"] for item in web[0]["items"]] == [btc]

    created = await create_watchlist(WatchlistCreateRequest(name="Swing ideas"), user={"id": uid})
    other = await _instrument("WX" + uuid4().hex[:6].upper())
    await add_watchlist_item(created["watchlist_id"], WatchlistItemRequest(instrument_id=other), user={"id": uid})
    listing = await _say(wc.watchlist_command, tg)
    assert "• My watchlist (default) — 1 instrument" in listing and symbol in listing
    assert "• Swing ideas — 1 instrument" in listing

    assert "already on" in await _say(wc.watchlist_command, tg, "add", symbol, "to", "my WATCHLIST")
    assert "Removed" in await _say(wc.watchlist_command, tg, "remove", symbol)
    assert (await _web_watchlists(uid))[0]["items"] == []


@pytest.mark.asyncio
async def test_ambiguous_or_unknown_symbols_never_guess_or_create_lists(isolated_postgres):
    uid, tg = await _linked_user()
    symbol = "AMB" + uuid4().hex[:5].upper()
    spot = await _instrument(symbol, "spot")
    perp = await _instrument(symbol, "perpetual")
    await _instrument("OLD" + symbol, active=False)

    reply = await _say(wc.watchlist_command, tg, "add", symbol)
    assert "matches several instruments" in reply and spot in reply and perp in reply
    assert "No active instrument" in await _say(wc.watchlist_command, tg, "add", "NOPE" + symbol)
    assert "No active instrument" in await _say(wc.watchlist_command, tg, "add", "OLD" + symbol)
    assert await _web_watchlists(uid) == []  # nothing created by failed adds
    assert "no watchlists yet" in await _say(wc.watchlist_command, tg, "remove", spot)
    assert await _web_watchlists(uid) == []

    assert "Added" in await _say(wc.watchlist_command, tg, "add", perp)  # an exact id resolves
    assert "no list named" in await _say(wc.watchlist_command, tg, "add", spot, "Missing", "list")


@pytest.mark.asyncio
async def test_deleting_a_list_needs_confirm_and_names_are_unique(isolated_postgres):
    uid, tg = await _linked_user()
    assert "Created “Majors”" in await _say(wc.watchlist_command, tg, "new", "Majors")
    assert "already have a list" in await _say(wc.watchlist_command, tg, "new", "Majors")
    assert "Give the list a name" in await _say(wc.watchlist_command, tg, "new")
    warning = await _say(wc.watchlist_command, tg, "delete", "majors")
    assert "Send /watchlist delete Majors confirm" in warning
    assert [w["name"] for w in await _web_watchlists(uid)] == ["Majors"]
    assert "Deleted “Majors”" in await _say(wc.watchlist_command, tg, "delete", "majors", "confirm")
    assert await _web_watchlists(uid) == []


@pytest.mark.asyncio
async def test_journal_entries_are_shared_and_deletes_need_confirm(isolated_postgres):
    from web.platform_api import JournalEntryRequest, create_journal_entry, journal_entries

    uid, tg = await _linked_user()
    saved = await _say(wc.journal_command, tg, "add", "Entered", "the", "breakout", "early", "#fomo", "#BTC")
    assert saved.startswith("✅ Saved journal entry ") and "#BTC #fomo" in saved
    web = (await journal_entries(limit=50, offset=0, user={"id": uid}))["entries"]
    assert len(web) == 1 and web[0]["notes"] == "Entered the breakout early" and web[0]["tags"] == ["BTC", "fomo"]

    await create_journal_entry(JournalEntryRequest(title="Plan held", notes="Waited for the retest", result_r=1.5,
                                                   tags=["discipline"]), user={"id": uid})
    listing = await _say(wc.journal_command, tg)
    assert "Plan held · +1.50R · #discipline" in listing and "Entered the breakout early" in listing

    short = web[0]["journal_entry_id"][:8]
    assert "Send /journal delete" in await _say(wc.journal_command, tg, "delete", short)
    assert len((await journal_entries(limit=50, offset=0, user={"id": uid}))["entries"]) == 2
    assert "Deleted journal entry" in await _say(wc.journal_command, tg, "delete", short, "confirm")
    assert len((await journal_entries(limit=50, offset=0, user={"id": uid}))["entries"]) == 1
    assert "Write the entry after add" in await _say(wc.journal_command, tg, "add", "#only_tags")


@pytest.mark.asyncio
async def test_one_account_cannot_see_or_delete_another_accounts_entries(isolated_postgres):
    from web.platform_api import JournalEntryRequest, create_journal_entry

    owner_uid, _ = await _linked_user()
    _, intruder_tg = await _linked_user()
    created = await create_journal_entry(JournalEntryRequest(notes="private note"), user={"id": owner_uid})
    short = created["journal_entry_id"][:8]
    assert "No entry of yours" in await _say(wc.journal_command, intruder_tg, "delete", short, "confirm")
    assert "private note" not in await _say(wc.journal_command, intruder_tg)
    assert "No entry of yours" in await _say(wc.journal_command, intruder_tg, "delete", "abc")  # too short


@pytest.mark.asyncio
async def test_group_chats_get_no_watchlist_or_journal_content():
    for command in (wc.watchlist_command, wc.journal_command):
        assert await _say(command, 123456789, chat_type="group") == wc.PRIVATE_ONLY
        assert await _say(command, 123456789, chat_type="supergroup") == wc.PRIVATE_ONLY


def test_hashtags_become_tags_and_unknown_actions_show_help():
    from services.platform.journal import split_hashtags

    assert split_hashtags("Cut the loser fast #discipline #risk_mgmt and moved on") == (
        "Cut the loser fast and moved on", ["discipline", "risk_mgmt"])
    assert split_hashtags("email a#b stays") == ("email a#b stays", [])


@pytest.mark.asyncio
async def test_unknown_subcommands_show_usage(isolated_postgres):
    _, tg = await _linked_user()
    assert await _say(wc.watchlist_command, tg, "frobnicate") == wc.WATCHLIST_HELP
    assert await _say(wc.journal_command, tg, "frobnicate") == wc.JOURNAL_HELP


def test_commands_are_registered_free_and_advertised():
    from core.tier_policy import COMMAND_MINIMUM_TIER
    from signalrank_telegram.command_catalog import COMMANDS

    names = {spec.name: spec for spec in COMMANDS}
    for name in ("watchlist", "journal"):
        assert names[name].tier == "FREE" and COMMAND_MINIMUM_TIER[name].value == "FREE"
    bot = open(os.path.join(os.path.dirname(__file__), "..", "signalrank_telegram", "bot.py"), encoding="utf-8").read()
    assert 'CommandHandler("watchlist", _audit_handler("watchlist", watchlist_command))' in bot
    assert 'CommandHandler("journal", _audit_handler("journal", journal_command))' in bot
