"""Advisory signals reach subscribers, marked PAPER ONLY (3 Nov 2026).

On 3 Nov two signals were stored (HYPEUSDT 1h short, score 62.8; BTCUSDT 5m
long, score 65.0) and no signal_deliveries row was written. Both were ML-advisory
(ml_recovery_mode, reason ml_advisory_mode) and below the 80-point tier minimum:
the recovery audience limited them to owner/admin, and every tier score check
refused them. With the ML model and the score floor advisory (owner decisions
of 2 and 3 Nov) they are the normal signal flow: delivered, marked PAPER ONLY,
and refused only for live execution.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: F401
from tests.test_signal_pipeline_postgres_20261030 import _signal, _stored, _vip_user, network_edges  # noqa: F401


def _advisory(asset: str) -> dict:
    return {**_signal(asset), "score": 63.0, "ml_probability": 0.04, "ml_recovery_mode": True,
            "ml_recovery_reason": "ml_advisory_mode", "ml_recovery_live_execution_allowed": False}


def test_advisory_signals_are_for_every_tier_and_starvation_recovery_stays_with_operators():
    from signalrank_telegram.tier_delivery import recovery_delivery_allowed

    advisory = {"ml_recovery_mode": True, "ml_recovery_reason": "ml_advisory_mode"}
    recovery = {"ml_recovery_mode": True, "ml_recovery_reason": "starvation"}
    for tier in ("free", "premium", "vip"):
        assert recovery_delivery_allowed(advisory, tier)
        assert not recovery_delivery_allowed(recovery, tier)
    assert recovery_delivery_allowed(recovery, "owner")


def test_tier_score_minimum_follows_the_score_floor_mode(monkeypatch):
    from signalrank_telegram.formatter import format_signal
    from signalrank_telegram.tier_delivery import TierDeliveryManager

    monkeypatch.setenv("SEGMENT_QUARANTINE_ENABLED", "1")
    monkeypatch.delenv("QUALITY_SCORE_GATE_MODE", raising=False)
    assert TierDeliveryManager().should_send_signal("vip", 63.0)
    text = format_signal({**_signal("ETHUSDT"), "score": 63.0}, display_tier="vip", user_tier="vip")
    assert text and "PAPER ONLY" in text
    monkeypatch.setenv("QUALITY_SCORE_GATE_MODE", "enforce")
    assert not TierDeliveryManager().should_send_signal("vip", 63.0)
    assert format_signal({**_signal("ETHUSDT"), "score": 63.0}, display_tier="vip", user_tier="vip") is None


@pytest.mark.asyncio
async def test_an_advisory_signal_is_reserved_and_sent_marked_paper_only(postgres_database, network_edges, monkeypatch):  # noqa: F811
    import signalrank_telegram.bot as bot
    from sqlalchemy import func, select

    from db.models import SignalDelivery
    from db.session import get_session

    monkeypatch.delenv("QUALITY_SCORE_GATE_MODE", raising=False)
    monkeypatch.delenv("ML_RECOVERY_DELIVERY_AUDIENCE", raising=False)
    monkeypatch.setenv("SEGMENT_QUARANTINE_ENABLED", "1")
    telegram_id = await _vip_user()
    asset = f"A{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    stored = await _stored(_advisory(asset))

    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    sent = [m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id]
    assert sent and "PAPER ONLY" in sent[0]["text"], [m["text"][:200] for m in sent]
    async with get_session() as session:
        rows = (await session.execute(select(func.count()).select_from(SignalDelivery)
                                      .where(SignalDelivery.signal_id == stored["signal_id"]))).scalar_one()
    assert rows >= 1


@pytest.mark.asyncio
async def test_enforce_mode_still_keeps_low_score_signals_from_subscribers(postgres_database, network_edges, monkeypatch):  # noqa: F811
    import signalrank_telegram.bot as bot

    monkeypatch.setenv("QUALITY_SCORE_GATE_MODE", "enforce")
    telegram_id = await _vip_user()
    asset = f"E{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    stored = await _stored({**_advisory(asset), "score": 79.0})
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 0
