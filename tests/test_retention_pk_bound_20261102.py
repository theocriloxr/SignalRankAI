"""Retention deletes are bounded by primary key (2 Nov 2026)."""
from __future__ import annotations

import asyncio

from db import storage_maintenance as sm


class _Res:
    def __init__(self, value=None, row=None):
        self._value, self._row = value, row

    def scalar(self):
        return self._value

    def first(self):
        return self._row


class _Session:
    """ids 1..100; ids below 40 are older than the cutoff."""

    def __init__(self):
        self.lookups = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "MAX(id)" in sql:
            return _Res(100)
        self.lookups += 1
        mid = max(1, int(params["mid"]))
        if mid > 100:
            return _Res(row=None)
        return _Res(row=(mid, mid < 40))


def test_binary_search_finds_first_recent_id():
    session = _Session()
    assert asyncio.run(sm._first_id_newer_than(session, 14)) == 40
    assert session.lookups <= 10


def test_every_delete_statement_is_bounded_by_id(monkeypatch):
    import inspect

    src = inspect.getsource(sm.run_learning_history_retention_once)
    assert src.count("AND id < CAST(:max_id AS BIGINT)") == 3
