from __future__ import annotations

import asyncio

from db.session import resolve_session_label


def test_explicit_db_session_label_is_preserved():
    assert resolve_session_label("telegram.command") == "telegram.command"


def test_missing_db_session_label_is_generated_from_caller():
    label = resolve_session_label(None)
    assert label
    assert label != "unlabelled"
    assert "test_missing_db_session_label_is_generated_from_caller" in label


def test_blank_db_session_label_never_becomes_unlabelled():
    label = resolve_session_label("   ")
    assert label
    assert label != "unlabelled"
