"""Signal cards show the setup's real record, not a claim (3 Nov 2026).

The owner wants signals sent without an 82 % target and the win rate shown as
the truth: each Premium/VIP card carries the setup's measured 60-day TP1 record
and the plan's break-even, whatever they are. No record is shown when there is
no current evidence; none is ever invented.
"""
from __future__ import annotations

import time

import pytest

from services import segment_evidence as se
from tests.test_master_p0_postgres_integration import postgres_database  # noqa: F401
from tests.test_telegram_message_contract_20261101 import telegram_html_errors


def _signal(**extra) -> dict:
    return {"signal_id": "5e7a1d2c-0000-4000-8000-000000000001", "asset": "BTCUSDT", "timeframe": "1h",
            "direction": "long", "entry": 100.0, "stop_loss": 98.0, "take_profit": [104.0, 106.0, 108.0],
            "score": 90.0, "strategy_name": "ATR Breakout", **extra}


@pytest.mark.parametrize("tier", ["premium", "vip"])
def test_cards_show_the_measured_record_and_break_even(tier):
    from signalrank_telegram.formatter import format_signal

    record = {"key": "atr breakout|1h|long", "trades": 1295, "wins": 663, "lower_bound": 0.489, "breakeven": 0.5}
    text = format_signal(_signal(segment_evidence=record), display_tier=tier, user_tier=tier)
    assert "663 of 1,295 similar setups reached TP1 (51%)" in text
    assert "This plan breaks even at 50%" in text
    assert telegram_html_errors(text) == []


def test_a_poor_record_is_shown_as_it_is():
    from signalrank_telegram.tier_signal_formatter import _setup_record_line

    line = _setup_record_line(_signal(segment_evidence={"trades": 400, "wins": 84, "breakeven": 0.36}))
    assert "84 of 400 similar setups reached TP1 (21%)" in line and "breaks even at 36%" in line


def test_no_record_no_line():
    from signalrank_telegram.tier_signal_formatter import _setup_record_line

    assert _setup_record_line(_signal()) == ""
    assert _setup_record_line(_signal(segment_evidence={"trades": 0, "wins": 0})) == ""


@pytest.mark.asyncio
async def test_signals_from_the_database_get_the_current_record(postgres_database):  # noqa: F811
    from sqlalchemy import text

    from db.session import get_session

    snapshot = {"computed_at": time.time(), "lookback_days": 60,
                "segments": {"atr breakout|1h|long": {"n": 200, "wins": 120}}}
    async with get_session() as session:
        await se.store_snapshot(session, snapshot)
        await session.commit()
    known, unknown = _signal(), _signal(strategy_name="Unseen Strategy")
    await se.attach_records([known, unknown])
    assert known["segment_evidence"]["trades"] == 200 and known["segment_evidence"]["wins"] == 120
    assert "segment_evidence" not in unknown  # no evidence: nothing shown, nothing invented

    stale = {**snapshot, "computed_at": time.time() - 10 * 86400}
    async with get_session() as session:
        await se.store_snapshot(session, stale)
        await session.commit()
        await session.execute(text("SELECT 1"))
    fresh = _signal()
    await se.attach_records([fresh])
    assert "segment_evidence" not in fresh


@pytest.mark.asyncio
async def test_the_signal_detail_api_returns_the_same_record(postgres_database):  # noqa: F811
    from db.session import get_session
    from web.platform_api import _setup_record

    snapshot = {"computed_at": time.time(), "lookback_days": 60,
                "segments": {"atr breakout|1h|long": {"n": 300, "wins": 99}}}
    async with get_session() as session:
        await se.store_snapshot(session, snapshot)
        await session.commit()
    row = {**_signal(), "take_profit": "[104.0, 106.0, 108.0]"}
    async with get_session() as session:
        record = await _setup_record(session, row)
        missing = await _setup_record(session, {**row, "strategy_name": "Unseen"})
        await session.rollback()
    assert record["trades"] == 300 and record["wins"] == 99 and record["lookback_days"] == 60
    assert record["breakeven"] == pytest.approx(1 / (1 + 0.5 * 2.0))
    assert missing is None
