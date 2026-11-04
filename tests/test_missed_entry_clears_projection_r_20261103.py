"""Production 2 Nov 2026: BCHUSDT missed_entry outcome kept r_multiple=-1.

A pending projection already carried a provisional R; the terminal
missed_entry write passed r_multiple=None and upsert_outcome kept the old
value, so a trade that never opened counted as an eligible -1R loss (32
eligible missed_entry rows with an R in production, avg -1.84R).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import db.pg_features as pgf

ROOT = Path(__file__).resolve().parents[1]


class _Scalars:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _Session:
    def __init__(self, existing):
        self.existing = existing
        self.added = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    async def execute(self, _stmt, _params=None):
        return SimpleNamespace(scalars=lambda: _Scalars(self.existing))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def _pending(r=-1.0, pct=-0.8):
    return SimpleNamespace(status="pending", r_multiple=r, percent=pct, closed_at=None, opened_at=None,
                           canonical_outcome="pending", terminal_version=0, meta={"provenance": "projection"},
                           id=7, duration_seconds=None)


@pytest.mark.parametrize("status", ["missed_entry", "expired"])
def test_terminal_no_trade_clears_a_projected_r(status):
    oc = _pending()
    session = _Session(oc)
    out = asyncio.run(pgf.upsert_outcome(session, "sig", status, r_multiple=None, percent=None,
                                         canonical_outcome=status, queue_notifications=False))
    assert out is oc
    assert oc.status == status
    assert oc.r_multiple is None and oc.percent is None
    assert oc.terminal_version == 1


def test_no_trade_status_ignores_a_supplied_r_on_insert():
    session = _Session(None)
    out = asyncio.run(pgf.upsert_outcome(session, "sig", "missed_entry", r_multiple=-1.0, percent=-0.5,
                                         canonical_outcome="missed_entry", queue_notifications=False))
    assert out.r_multiple is None and out.percent is None


def test_real_exit_keeps_its_r():
    oc = _pending()
    asyncio.run(pgf.upsert_outcome(_Session(oc), "sig", "sl", r_multiple=-1.0, percent=-0.8,
                                   canonical_outcome="loss", queue_notifications=False))
    assert oc.r_multiple == -1.0


def test_scorecard_issued_source_skips_no_trade_outcomes():
    source = (ROOT / "services" / "strategy_scorecard.py").read_text(encoding="utf-8")
    block = source[source.index("FROM signals s JOIN outcomes o"):source.index('{"cutoff": cutoff}')]
    assert "NOT IN ('missed_entry', 'missed', 'expired')" in block
    assert "lower(COALESCE(o.status, ''))" in block
    assert "lower(COALESCE(o.canonical_outcome, ''))" in block


# 4 Nov 2026: the bot's candle scan writes a terminal status without a canonical
# outcome; the projection's canonical 'pending' stayed on a closed loss (ZECUSDT
# 66b151e6: status=sl, r=-1, canonical_outcome=pending), so the ledger counted it open.


def test_terminal_write_without_canonical_replaces_pending():
    oc = _pending()
    asyncio.run(pgf.upsert_outcome(_Session(oc), "sig", "sl", r_multiple=-1.0, percent=-1.7,
                                   meta={"source": "candle_scan", "tp_hit_index": None},
                                   queue_notifications=False))
    assert oc.status == "sl"
    assert oc.canonical_outcome == "loss"
    assert oc.r_multiple == -1.0


@pytest.mark.parametrize(
    "status,meta,expected",
    [
        ("tp3", {"tp_hit_index": 3}, "win"),
        ("sl", {"tp_hit_index": 1}, "partial_win"),
        ("time_stop", {}, "time_stop"),
        ("missed_entry", {}, "missed_entry"),
    ],
)
def test_derived_canonical_follows_the_tracker_mapping(status, meta, expected):
    oc = _pending()
    asyncio.run(pgf.upsert_outcome(_Session(oc), "sig", status, r_multiple=None, percent=None, meta=meta,
                                   queue_notifications=False))
    assert oc.canonical_outcome == expected


def test_supplied_or_settled_canonical_is_not_overwritten():
    oc = _pending()
    asyncio.run(pgf.upsert_outcome(_Session(oc), "sig", "sl", r_multiple=-1.0, canonical_outcome="partial_win",
                                   queue_notifications=False))
    assert oc.canonical_outcome == "partial_win"
    oc2 = _pending()
    oc2.canonical_outcome = "partial_win"
    asyncio.run(pgf.upsert_outcome(_Session(oc2), "sig", "sl", r_multiple=-1.0, queue_notifications=False))
    assert oc2.canonical_outcome == "partial_win"


def test_non_terminal_progress_keeps_pending():
    oc = _pending()
    asyncio.run(pgf.upsert_outcome(_Session(oc), "sig", "tp1", r_multiple=None, queue_notifications=False))
    assert oc.canonical_outcome == "pending"


def test_insert_of_a_terminal_status_gets_a_canonical():
    out = asyncio.run(pgf.upsert_outcome(_Session(None), "sig", "sl", r_multiple=-1.0, queue_notifications=False))
    assert out.canonical_outcome == "loss"
