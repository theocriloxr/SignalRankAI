"""Trade journal shared by the web workspace and the Telegram bot (CX-CHAN-01).

Entries are private to the canonical account. Callers own the transaction:
these functions never commit.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

NOTES_MAX = 20000
TAGS_MAX = 20
SHORT_ID_MIN = 6


def clean_tags(values: Any) -> list[str]:
    return sorted({str(value).strip()[:64] for value in (values or []) if str(value).strip()})[:TAGS_MAX]


def split_hashtags(note: str) -> tuple[str, list[str]]:
    """Telegram entry text: ``#tag`` words become tags; the rest is the note."""
    tags = re.findall(r"(?<!\w)#([A-Za-z0-9_][A-Za-z0-9_-]{0,63})", note or "")
    body = re.sub(r"(?<!\w)#[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", "", note or "")
    return " ".join(body.split()), clean_tags(tags)


async def list_entries(session: Any, user_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                "SELECT journal_entry_id,signal_id,paper_position_id,title,notes,emotion,mistake_category,"
                "plan_adherence,result_r,tags,occurred_at,created_at,updated_at "
                "FROM journal_entries WHERE user_id=:uid ORDER BY occurred_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"uid": int(user_id), "limit": int(limit), "offset": int(offset)},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def create_entry(
    session: Any,
    user_id: int,
    *,
    notes: str = "",
    title: str | None = None,
    signal_id: str | None = None,
    paper_position_id: str | None = None,
    emotion: str | None = None,
    mistake_category: str | None = None,
    plan_adherence: int | None = None,
    result_r: float | None = None,
    tags: Any = (),
    occurred_at: datetime | None = None,
) -> str:
    entry_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO journal_entries("
            "journal_entry_id,user_id,signal_id,paper_position_id,title,notes,emotion,mistake_category,"
            "plan_adherence,result_r,tags,occurred_at"
            ") VALUES(:entry_id,:uid,:signal_id,:position_id,:title,:notes,:emotion,:mistake,"
            ":adherence,:result_r,CAST(:tags AS JSONB),COALESCE(:occurred_at,NOW()))"
        ),
        {
            "entry_id": entry_id,
            "uid": int(user_id),
            "signal_id": signal_id,
            "position_id": paper_position_id,
            "title": title,
            "notes": str(notes or "")[:NOTES_MAX],
            "emotion": emotion,
            "mistake": mistake_category,
            "adherence": plan_adherence,
            "result_r": result_r,
            "tags": json.dumps(clean_tags(tags), separators=(",", ":")),
            "occurred_at": occurred_at,
        },
    )
    return entry_id


async def delete_entry(session: Any, user_id: int, entry_id: str) -> bool:
    result = await session.execute(
        text("DELETE FROM journal_entries WHERE journal_entry_id=:entry_id AND user_id=:uid"),
        {"entry_id": str(entry_id), "uid": int(user_id)},
    )
    return bool(result.rowcount)


async def match_entries(session: Any, user_id: int, short_id: str) -> list[str]:
    """Entry ids in this account starting with ``short_id`` (at least six characters)."""
    prefix = str(short_id or "").strip().lower()
    if len(prefix) < SHORT_ID_MIN or not re.fullmatch(r"[0-9a-f-]+", prefix):
        return []
    rows = (
        await session.execute(
            text("SELECT journal_entry_id FROM journal_entries WHERE user_id=:uid "
                 "AND journal_entry_id LIKE :prefix ORDER BY occurred_at DESC LIMIT 3"),
            {"uid": int(user_id), "prefix": prefix + "%"},
        )
    ).all()
    return [str(row[0]) for row in rows]


__all__ = [
    "NOTES_MAX", "clean_tags", "create_entry", "delete_entry", "list_entries", "match_entries", "split_hashtags",
]
