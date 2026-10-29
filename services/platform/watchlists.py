"""Watchlists shared by the web workspace and the Telegram bot (CX-CHAN-01).

Both channels read and write the same rows for the same canonical account, so
a list built on the web appears in Telegram and the other way round. Callers
own the transaction: these functions never commit.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import text

DEFAULT_NAME = "My watchlist"
NAME_MAX = 100


class WatchlistError(ValueError):
    """Refusal with a stable code: ``exists``, ``watchlist_not_found`` or ``instrument_not_found``."""


def clean_name(name: Any) -> str:
    value = " ".join(str(name or "").split())
    if not value or len(value) > NAME_MAX:
        raise WatchlistError("invalid_name")
    return value


async def list_watchlists(session: Any, user_id: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "SELECT w.watchlist_id,w.name,w.is_default,w.created_at,w.updated_at,"
                "COALESCE(jsonb_agg(jsonb_build_object('instrument_id',wi.instrument_id)) FILTER (WHERE wi.instrument_id IS NOT NULL),'[]'::jsonb) AS items "
                "FROM watchlists w LEFT JOIN watchlist_items wi ON wi.watchlist_id=w.watchlist_id "
                "WHERE w.user_id=:uid GROUP BY w.watchlist_id ORDER BY w.is_default DESC,w.created_at"
            ),
            {"uid": int(user_id)},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def create_watchlist(session: Any, user_id: int, name: Any, *, is_default: bool = False) -> dict[str, Any]:
    clean = clean_name(name)
    watchlist_id = str(uuid4())
    try:
        async with session.begin_nested():
            await session.execute(
                text("INSERT INTO watchlists(watchlist_id,user_id,name,is_default) VALUES(:wid,:uid,:name,:default)"),
                {"wid": watchlist_id, "uid": int(user_id), "name": clean, "default": bool(is_default)},
            )
    except Exception as exc:
        raise WatchlistError("exists") from exc
    return {"watchlist_id": watchlist_id, "name": clean}


async def delete_watchlist(session: Any, user_id: int, watchlist_id: str) -> bool:
    result = await session.execute(
        text("DELETE FROM watchlists WHERE watchlist_id=:id AND user_id=:uid"),
        {"id": str(watchlist_id), "uid": int(user_id)},
    )
    return bool(result.rowcount)


async def add_item(session: Any, user_id: int, watchlist_id: str, instrument_id: str) -> bool:
    """Add an instrument; returns False when it was already on the list."""
    owner = (
        await session.execute(
            text("SELECT 1 FROM watchlists WHERE watchlist_id=:wid AND user_id=:uid"),
            {"wid": str(watchlist_id), "uid": int(user_id)},
        )
    ).first()
    if not owner:
        raise WatchlistError("watchlist_not_found")
    instrument = (
        await session.execute(text("SELECT 1 FROM instruments WHERE instrument_id=:iid"), {"iid": str(instrument_id)})
    ).first()
    if not instrument:
        raise WatchlistError("instrument_not_found")
    result = await session.execute(
        text("INSERT INTO watchlist_items(watchlist_id,instrument_id) VALUES(:wid,:iid) ON CONFLICT DO NOTHING"),
        {"wid": str(watchlist_id), "iid": str(instrument_id)},
    )
    return bool(result.rowcount)


async def remove_item(session: Any, user_id: int, watchlist_id: str, instrument_id: str) -> bool:
    result = await session.execute(
        text(
            "DELETE FROM watchlist_items wi USING watchlists w WHERE wi.watchlist_id=w.watchlist_id "
            "AND wi.watchlist_id=:watchlist_id AND wi.instrument_id=:instrument_id AND w.user_id=:uid"
        ),
        {"watchlist_id": str(watchlist_id), "instrument_id": str(instrument_id), "uid": int(user_id)},
    )
    return bool(result.rowcount)


async def find_watchlist(session: Any, user_id: int, name: Any) -> dict[str, Any] | None:
    """Case-insensitive name lookup within one account."""
    row = (
        await session.execute(
            text("SELECT watchlist_id,name,is_default FROM watchlists WHERE user_id=:uid AND lower(name)=lower(:name) "
                 "ORDER BY created_at LIMIT 1"),
            {"uid": int(user_id), "name": " ".join(str(name or "").split())},
        )
    ).mappings().first()
    return dict(row) if row else None


async def default_watchlist(session: Any, user_id: int) -> dict[str, Any]:
    """The account's default list, else its oldest, else a new ``My watchlist``."""
    row = (
        await session.execute(
            text("SELECT watchlist_id,name,is_default FROM watchlists WHERE user_id=:uid "
                 "ORDER BY is_default DESC,created_at LIMIT 1"),
            {"uid": int(user_id)},
        )
    ).mappings().first()
    if row:
        return dict(row)
    created = await create_watchlist(session, user_id, DEFAULT_NAME, is_default=True)
    return {**created, "is_default": True}


def _symbol_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


async def resolve_instrument(session: Any, query: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Resolve a typed symbol or instrument id to one instrument.

    Returns ``(match, candidates)``: an exact instrument id wins; otherwise one
    active instrument whose symbol matches. Several matches are returned as
    candidates instead of guessing (a spot pair and a perpetual can share a symbol).
    """
    raw = str(query or "").strip()[:128]
    key = _symbol_key(raw)
    if not raw or not key:
        return None, []
    rows = (
        await session.execute(
            text(
                "SELECT instrument_id,display_symbol,canonical_symbol,asset_class,instrument_type,tradable "
                "FROM instruments WHERE instrument_id=:raw OR (active=TRUE AND ("
                "upper(regexp_replace(canonical_symbol,'[^A-Za-z0-9]','','g'))=:key "
                "OR upper(regexp_replace(display_symbol,'[^A-Za-z0-9]','','g'))=:key)) "
                "ORDER BY (instrument_id=:raw) DESC,tradable DESC,instrument_id LIMIT 6"
            ),
            {"raw": raw, "key": key},
        )
    ).mappings().all()
    candidates = [dict(row) for row in rows]
    if candidates and candidates[0]["instrument_id"] == raw:
        return candidates[0], []
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


async def instrument_labels(session: Any, instrument_ids: list[str]) -> dict[str, str]:
    ids = sorted({str(value) for value in instrument_ids if value})
    if not ids:
        return {}
    rows = (
        await session.execute(
            text("SELECT instrument_id,display_symbol FROM instruments WHERE instrument_id = ANY(:ids)"),
            {"ids": ids},
        )
    ).all()
    return {str(row[0]): str(row[1] or row[0]) for row in rows}


__all__ = [
    "DEFAULT_NAME", "WatchlistError", "add_item", "clean_name", "create_watchlist", "default_watchlist",
    "delete_watchlist", "find_watchlist", "instrument_labels", "list_watchlists", "remove_item",
    "resolve_instrument",
]
