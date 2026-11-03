"""Every place a user sees their results shows the same figures (3 Nov 2026).

/stats and /mystats counted any tp* outcome as a win over all outcome rows
(open, missed and expired included), ignored the audited ledger exclusions
(0058: |R| > 10 kept out of performance) and counted a signal twice when it was
delivered twice. /performance and the web page read the proof ledger. All three
now read services.performance_ledger.ledger_summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: F401
from tests.test_signal_pipeline_postgres_20261030 import _signal, _stored, _vip_user, network_edges  # noqa: F401

# (bucket, final R, included)
ROWS = [("TP3", 2.5, True), ("TP3", 3.0, True), ("STOPPED_AT_TP1", 0.75, True), ("BREAKEVEN", 0.0, True),
        ("SL", -1.0, True), ("SL", -1.0, True), ("ACTIVE", None, True), ("MISSED_ENTRY", None, True),
        ("SL", -63.0, False)]  # audited exclusion: must not count anywhere


async def _seed(telegram_id: int, prices: dict) -> int:
    import signalrank_telegram.bot as bot
    from sqlalchemy import select

    from db.models import PerformanceLedgerEntry, SignalDelivery, User
    from db.session import get_session

    async with get_session() as session:
        user_id = (await session.execute(select(User.id).where(User.telegram_user_id == telegram_id))).scalar_one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for bucket, r_value, included in ROWS:
        asset = f"C{uuid4().hex[:6].upper()}USDT"
        prices[asset] = 100.0
        stored = await _stored(_signal(asset))
        assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
        async with get_session() as session:
            delivery_id = (await session.execute(select(SignalDelivery.id).where(
                SignalDelivery.signal_id == stored["signal_id"], SignalDelivery.user_id == user_id))).scalar_one()
            session.add(PerformanceLedgerEntry(
                user_id=user_id, signal_id=stored["signal_id"], delivery_id=delivery_id, domain="test-consistency",
                environment="test", delivery_confirmed_at=now, asset=asset, timeframe="15m", direction="long",
                primary_bucket=bucket, entry_status="filled", final_realized_r=r_value, outcome_source="test",
                calculation_policy_version="t", signal_plan_version="t", included=included,
                exclusion_reason=None if included else "degenerate_stop_abs_r_gt_10", snapshot_hash=uuid4().hex))
            await session.commit()
    return user_id


@pytest.mark.asyncio
async def test_web_stats_and_mystats_show_the_same_results(postgres_database, network_edges):  # noqa: F811
    from db.session import get_session
    from services.performance_ledger import format_ledger_summary_lines, ledger_summary
    from signalrank_telegram.commands import mystats_command, stats_command
    from web.platform_api import performance

    telegram_id = await _vip_user()
    user_id = await _seed(telegram_id, network_edges.prices)

    async with get_session() as session:
        summary, _ = await ledger_summary(session, user_id)
        await session.rollback()
    assert summary["wins"] == 2 and summary["losses"] == 2 and summary["partial_wins"] == 1
    assert summary["breakeven"] == 1 and summary["open"] == 1 and summary["not_triggered"] == 1
    assert summary["win_rate"] == pytest.approx(0.5)
    assert summary["total_r"] == pytest.approx(2.5 + 3.0 + 0.75 + 0 - 1 - 1)  # the excluded -63R stays out

    web = await performance({"id": user_id, "tier": "vip"})
    assert {k: web["summary"][k] for k in summary} == summary

    replies: list[str] = []

    async def reply_text(text, **kwargs):
        replies.append(text)

    update = SimpleNamespace(effective_user=SimpleNamespace(id=telegram_id),
                             message=SimpleNamespace(reply_text=reply_text))
    await stats_command(update, SimpleNamespace(args=[]))
    await mystats_command(update, SimpleNamespace(args=[]))
    expected = format_ledger_summary_lines(summary)
    for text in replies:
        for line in expected:
            assert line in text.replace("&amp;", "&"), (line, text)
        assert "-63" not in text
