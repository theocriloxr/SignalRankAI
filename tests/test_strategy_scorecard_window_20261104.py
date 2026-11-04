"""The scorecard's shadow scan keeps the newest rows when its page budget is short (4 Nov 2026).

Production evidence: the 30-day lookback held ~2.4 M decision_log ids while the scan
budget is 400 pages x 5,000 ids, so the forward scan stopped around 2 Nov 10:00 UTC.
Three rebuilds on 3-4 Nov reported the same ``rows_used`` (97,577) and none of the rows
labelled after the 3 Nov labelling change reached the scorecard.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta

from services import strategy_scorecard as sc


def test_whole_lookback_is_scanned_when_it_fits():
    assert sc.shadow_scan_start(1_000, 5_000, 1_000, 10) == (1_000, None)
    assert sc.shadow_scan_start(1, 10_000, 1_000, 10) == (1, None)


def test_newest_rows_are_kept_when_the_budget_is_short():
    start, original = sc.shadow_scan_start(1_600_000, 4_059_478, 5_000, 400)
    assert original == 1_600_000
    assert start == 4_059_478 - 2_000_000 + 1
    # the budget covers exactly the newest ids up to max_id
    assert 4_059_478 - start + 1 == 2_000_000


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class _FakeDecisionLog:
    """decision_log with ids 1..max_id, one row per id, created one minute apart."""

    def __init__(self, max_id: int, start: datetime):
        self.max_id = max_id
        self.start = start
        self.scanned: list[tuple[int, int]] = []

    def created(self, i: int) -> datetime:
        return self.start + timedelta(minutes=i)

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "FROM signals s JOIN outcomes" in sql:
            return _Result([])
        if "MAX(id)" in sql:
            return _Result(scalar=self.max_id)
        if "ORDER BY id LIMIT 1" in sql:
            mid = max(1, int(params["mid"]))
            return _Result([(mid, self.created(mid))] if mid <= self.max_id else [])
        after, page = int(params["after"]), int(params["page"])
        self.scanned.append((after + 1, after + page))
        rows = []
        for i in range(max(1, after + 1), min(after + page, self.max_id) + 1):
            rows.append((i, "BTCUSDT", "1h", self.created(i), "long", "100", "99", [102], "sl", "EMA Trend"))
        return _Result(rows)


def _install(monkeypatch, log: _FakeDecisionLog, now: datetime):
    import db.session
    import utils.timeutils

    @contextlib.asynccontextmanager
    async def fake_session(**_kwargs):
        yield log

    monkeypatch.setattr(db.session, "get_session", fake_session)
    monkeypatch.setattr(utils.timeutils, "now_utc_naive", lambda: now)


def test_load_rows_reads_the_newest_rows_when_lookback_exceeds_budget(monkeypatch):
    start = datetime(2026, 10, 1)
    log = _FakeDecisionLog(max_id=1_000, start=start)
    now = log.created(1_000) + timedelta(minutes=1)
    _install(monkeypatch, log, now)
    monkeypatch.setenv("STRATEGY_SCORECARD_PAGE_ROWS", "500")
    monkeypatch.setenv("STRATEGY_SCORECARD_MAX_PAGES", "1")

    rows = asyncio.run(sc._load_rows(lookback_days=30))

    assert log.scanned == [(501, 1_000)]
    assert len(rows) == 500
    newest = max(r["bar"] for r in rows)
    assert newest == sc.bar_index(log.created(1_000), "1h")
    assert sc.LAST_SCAN == {"scan_from_id": 501, "max_id": 1_000, "truncated": True}


def test_load_rows_scans_the_whole_lookback_when_it_fits(monkeypatch):
    start = datetime(2026, 10, 1)
    log = _FakeDecisionLog(max_id=1_000, start=start)
    now = log.created(1_000) + timedelta(minutes=1)
    _install(monkeypatch, log, now)
    monkeypatch.setenv("STRATEGY_SCORECARD_PAGE_ROWS", "500")
    monkeypatch.setenv("STRATEGY_SCORECARD_MAX_PAGES", "10")

    rows = asyncio.run(sc._load_rows(lookback_days=30))

    assert log.scanned[0][0] <= 1
    assert len(rows) == 1_000
    assert sc.LAST_SCAN["truncated"] is False
