"""The signal pipeline end to end on real PostgreSQL (30 Oct 2026).

save -> deliver once -> track entry and targets -> outcome -> recipient
notifications -> /proof. Only the network edges are replaced: the Telegram Bot
API and the market-data quote providers. Everything else (persistence, dedup,
delivery ledger, lifecycle writer, outcome projection, notification ledger,
reporting queries) runs against the migrated schema. Skipped without an isolated
PostgreSQL; required when SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: F401


class _Telegram:
    """Records Bot API calls; every send succeeds with a new message id."""

    def __init__(self):
        self.sent: list[dict] = []

    def bot_class(self):
        outer = self

        class FakeBot:
            def __init__(self, *args, **kwargs):
                pass

            async def send_message(self, chat_id=None, text=None, **kwargs):
                outer.sent.append({"chat_id": int(chat_id), "text": str(text), **kwargs})
                return SimpleNamespace(message_id=700000 + len(outer.sent), chat=SimpleNamespace(id=int(chat_id)))

            async def edit_message_text(self, *args, **kwargs):
                return True

            async def edit_message_reply_markup(self, *args, **kwargs):
                return True

        return FakeBot


def _quote(symbol: str, price: float):
    from data.provider_types import LivePriceQuote

    now = time.time()
    return LivePriceQuote(symbol, price, "test-provider", now, 1, asset_class="crypto", source_timestamp=now,
                          received_at=now, completed_at=now, market_status="open", session="continuous",
                          provider_health="healthy", quote_kind="bid_ask", bid=price - 0.01, ask=price + 0.01)


async def _vip_user() -> int:
    from datetime import timedelta

    from db.models import Subscription, User
    from db.session import get_session

    telegram_id = 7_100_000_000 + int(uuid4().hex[:7], 16)
    async with get_session() as session:
        user = User(telegram_user_id=telegram_id, username=f"pipeline-{telegram_id}", tier="vip", timezone="UTC")
        session.add(user)
        await session.flush()
        session.add(Subscription(user_id=user.id, tier="vip", status="active",
                                 expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)))
        await session.commit()
    return telegram_id


def _signal(asset: str) -> dict:
    return {"asset": asset, "symbol": asset, "timeframe": "15m", "direction": "long", "trade_profile": "intraday",
            "entry": 100.0, "stop_loss": 98.0, "take_profit": [102.0, 104.0, 106.0],
            "take_profits": [102.0, 104.0, 106.0], "score": 92.0, "rr_ratio": 3.0, "rr_estimate": 3.0,
            "strategy_name": "pipeline-audit", "strategy_group": "pipeline-audit", "regime": "trending",
            "strength": 1, "current_price": 100.0, "created_at": datetime.now(timezone.utc).isoformat()}


async def _stored(payload: dict) -> dict:
    """Run the engine's quality gate, then persist as store_signal_compat does before delivery."""
    from core.signal_quality_gate import evaluate_signal_quality
    from db.pg_features import get_or_create_signal
    from db.session import get_session

    decision = evaluate_signal_quality(payload, execution=False)
    assert decision.ok, decision.reasons
    payload = {**payload, "quality_gate_version": decision.version, "quality_gate_passed": True,
               "thesis_fingerprint": decision.thesis_fingerprint, "quality_tp1_rr": decision.tp1_rr,
               "quality_final_rr": decision.final_rr}
    async with get_session() as session:
        row = await get_or_create_signal(session, payload)
        await session.commit()
    return {**payload, "signal_id": str(row.signal_id)}


@pytest.fixture
def network_edges(monkeypatch):
    """Replace only the Telegram Bot API and the quote providers."""
    import data.market_hours as hours
    import engine.delivery_freshness as freshness
    import engine.realtime_outcome_tracker as tracker
    import engine.stale_signal_validator as stale
    import signalrank_telegram.bot as bot
    from config import config

    telegram = _Telegram()
    prices: dict[str, float] = {}
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "unit-test-placeholder")
    monkeypatch.setattr(bot, "_require_telegram_token", lambda: "unit-test-placeholder")
    monkeypatch.setattr(bot, "Bot", telegram.bot_class())
    monkeypatch.setattr("telegram.Bot", telegram.bot_class())
    monkeypatch.setattr(hours, "get_market_session_status",
                        lambda _symbol: SimpleNamespace(is_open=True, reason="synthetic open session"))

    async def final_quote(symbol):
        return _quote(symbol, prices.get(str(symbol).upper(), 100.0))

    async def outcome_quote(symbol):
        price = prices.get(str(symbol).upper())  # other tests' signals stay unpriced (untrusted)
        return tracker.OutcomePriceObservation(asset=str(symbol).upper(), price=price, provider="test-provider",
                                               quote_time=datetime.now(timezone.utc).isoformat(),
                                               provider_trusted=price is not None, request_id=uuid4().hex)

    async def no_candle_range(symbol):
        return None, None, None, False

    async def stale_check_price(symbol):
        return prices.get(str(symbol).upper(), 100.0)

    monkeypatch.setattr(freshness, "_fetch_final_live_quote", final_quote)
    monkeypatch.setattr(stale, "_get_live_price_async", stale_check_price)
    monkeypatch.setattr(stale, "_get_secondary_price", stale_check_price)
    monkeypatch.setattr(tracker, "_get_outcome_quote", outcome_quote)
    monkeypatch.setattr(tracker, "_get_recent_outcome_range", no_candle_range)
    monkeypatch.setenv("LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED", "1")
    return SimpleNamespace(telegram=telegram, prices=prices)


@pytest.mark.asyncio
async def test_a_signal_is_saved_delivered_once_tracked_and_reported(postgres_database, network_edges):  # noqa: F811
    import signalrank_telegram.bot as bot
    from db.models import Outcome, Signal, SignalDelivery, SignalLifecycle, User
    from db.session import get_session
    from engine.realtime_outcome_tracker import reconcile_signal_now

    telegram_id = await _vip_user()
    asset = f"P{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0

    # Delivery: saved once, one Telegram message, delivery ledger carries the proof.
    stored = await _stored(_signal(asset))
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    to_user = [m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id]
    signal_messages = [m for m in to_user if "SIGNAL" in m["text"] and asset in m["text"]]
    assert len(signal_messages) == 1, [m["text"][:300] for m in to_user]
    after_delivery = len(to_user)  # the signal plus its execution-readiness note
    async with get_session() as session:
        signal = (await session.execute(select(Signal).where(Signal.asset == asset))).scalar_one()
        signal_id = str(signal.signal_id)
        assert (signal.entry, signal.stop_loss, signal.direction) == (100.0, 98.0, "long")
        delivery = (await session.execute(
            select(SignalDelivery).join(User, User.id == SignalDelivery.user_id)
            .where(User.telegram_user_id == telegram_id, SignalDelivery.signal_id == signal_id))).scalar_one()
        assert delivery.sent_ok is True and str(delivery.delivery_state).lower() in {"sent", "confirmed", "delivered"}
        assert int(delivery.telegram_message_id) == 700000 + network_edges.telegram.sent.index(signal_messages[0]) + 1

    # The same signal again is not sent twice.
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 0
    assert len([m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id]) == after_delivery

    # Tracking: entry, then each target, through the shared lifecycle writer.
    for price in (100.0, 102.05, 104.05, 106.05):
        network_edges.prices[asset] = price
        assert await reconcile_signal_now(signal_id)
    async with get_session() as session:
        lifecycle = (await session.execute(select(SignalLifecycle).where(SignalLifecycle.signal_id == signal_id))).scalar_one()
        outcome = (await session.execute(select(Outcome).where(Outcome.signal_id == signal_id))).scalar_one()
        assert lifecycle.entry_touched_at is not None and lifecycle.tp1_hit_at is not None
        assert str(lifecycle.state).upper().startswith("TP3") or lifecycle.closed_at is not None, lifecycle.state
        assert str(outcome.status).lower() in {"tp3", "tp"}, outcome.status
        assert float(outcome.r_multiple or 0) == pytest.approx(3.0, abs=0.1)

    # The recipient heard about the outcome, once.
    outcome_messages = [m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id][after_delivery:]
    assert outcome_messages, "no outcome notification reached the recipient"
    assert any(asset in m["text"] for m in outcome_messages), [m["text"][:200] for m in outcome_messages]
    await reconcile_signal_now(signal_id)  # a repeat observation sends nothing new
    assert [m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id][after_delivery:] == outcome_messages

    # Reporting: /proof counts it as a verified win (failed silently before on PostgreSQL).
    from signalrank_telegram.commands import proof_command

    replies: list[str] = []

    async def reply_text(text, **kwargs):
        replies.append(text)

    update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text, chat=SimpleNamespace(type="private")),
                             effective_user=SimpleNamespace(id=telegram_id), effective_chat=SimpleNamespace(type="private", id=telegram_id))
    await proof_command(update, SimpleNamespace(args=[]))
    assert replies and f"{asset} • 15m • {str(outcome.status).upper()}" in replies[-1], replies


@pytest.mark.asyncio
async def test_a_losing_short_reaches_every_recipient_once(postgres_database, network_edges):  # noqa: F811
    import signalrank_telegram.bot as bot
    from db.models import Outcome, Signal, SignalDelivery
    from db.session import get_session
    from engine.realtime_outcome_tracker import reconcile_signal_now

    first, second = await _vip_user(), await _vip_user()
    asset = f"S{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    short = await _stored({**_signal(asset), "direction": "short", "stop_loss": 102.0,
                           "take_profit": [98.0, 96.0, 94.0], "take_profits": [98.0, 96.0, 94.0]})
    for recipient in (first, second):
        assert await bot.dispatch_signals_async([dict(short)], recipient) == 1
    async with get_session() as session:
        signal_ids = (await session.execute(select(Signal.signal_id).where(Signal.asset == asset))).scalars().all()
        assert len(signal_ids) == 1, "the same analysed signal must be stored once for both recipients"
        signal_id = str(signal_ids[0])
        deliveries = (await session.execute(select(func.count()).select_from(SignalDelivery)
                                            .where(SignalDelivery.signal_id == signal_id, SignalDelivery.sent_ok.is_(True)))).scalar()
        assert deliveries == 2
    before = {r: len([m for m in network_edges.telegram.sent if m["chat_id"] == r]) for r in (first, second)}

    for price in (100.0, 102.05):
        network_edges.prices[asset] = price
        assert await reconcile_signal_now(signal_id)
    await reconcile_signal_now(signal_id)
    async with get_session() as session:
        outcome = (await session.execute(select(Outcome).where(Outcome.signal_id == signal_id))).scalar_one()
    assert str(outcome.status).lower() == "sl" and float(outcome.r_multiple) == pytest.approx(-1.0, abs=0.05)
    for recipient in (first, second):
        after = [m for m in network_edges.telegram.sent if m["chat_id"] == recipient][before[recipient]:]
        assert len(after) == 1 and asset in after[0]["text"], [m["text"][:160] for m in after]


@pytest.mark.asyncio
async def test_an_engine_stored_signal_is_delivered_to_each_recipient(postgres_database, network_edges):  # noqa: F811
    """The engine stores a signal first (store_signal_compat), then dispatches it per user."""
    import signalrank_telegram.bot as bot
    from db.models import Signal, SignalDelivery
    from db.session import get_session

    first, second = await _vip_user(), await _vip_user()
    asset = f"E{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    stored = await _stored(_signal(asset))

    sent = [await bot.dispatch_signals_async([dict(stored)], recipient) for recipient in (first, second)]
    async with get_session() as session:
        rows = (await session.execute(select(Signal.signal_id).where(Signal.asset == asset))).scalars().all()
        delivered = (await session.execute(select(func.count()).select_from(SignalDelivery).where(
            SignalDelivery.signal_id == stored["signal_id"], SignalDelivery.sent_ok.is_(True)))).scalar()
    assert rows == [stored["signal_id"]]
    assert sent == [1, 1] and delivered == 2


@pytest.mark.asyncio
async def test_a_stored_identity_is_reused_only_for_its_own_open_levels(postgres_database):  # noqa: F811
    from sqlalchemy import update

    from db.models import Signal
    from db.pg_features import SignalDedupBlocked, get_or_create_signal
    from db.session import get_session

    stored = await _stored(_signal(f"I{uuid4().hex[:6].upper()}USDT"))
    async with get_session() as session:
        assert str((await get_or_create_signal(session, dict(stored))).signal_id) == stored["signal_id"]
        with pytest.raises(SignalDedupBlocked, match="signal_id_payload_mismatch"):
            await get_or_create_signal(session, {**stored, "entry": 101.0})
        # A genuinely new candidate (no stored identity) is still suppressed.
        with pytest.raises(SignalDedupBlocked, match="min_interval"):
            await get_or_create_signal(session, {k: v for k, v in stored.items() if k != "signal_id"})
        await session.execute(update(Signal).where(Signal.signal_id == stored["signal_id"]).values(expired=True))
        await session.commit()
    async with get_session() as session:
        with pytest.raises(SignalDedupBlocked, match="signal_closed"):
            await get_or_create_signal(session, dict(stored))


@pytest.mark.asyncio
async def test_a_free_user_receives_one_pool_signal(postgres_database, network_edges, caplog):  # noqa: F811
    """Free delivery picks at random from the stored pool, then runs the same final-send checks.

    It used to send while holding its reservation session, so the sender's own
    sessions waited on it (one critical lane) and timed out after 5 s.
    """
    import signalrank_telegram.bot as bot
    from db.models import Signal, SignalDelivery, User
    from db.session import get_session

    telegram_id = 7_200_000_000 + int(uuid4().hex[:7], 16)
    async with get_session() as session:
        session.add(User(telegram_user_id=telegram_id, username=f"free-{telegram_id}", tier="free", timezone="UTC"))
        await session.commit()
    asset = f"F{uuid4().hex[:6].upper()}USDT"
    stored = await _stored(_signal(asset))
    async with get_session() as session:  # every open pool signal is priced at its entry
        for pool_asset, entry in (await session.execute(select(Signal.asset, Signal.entry))).all():
            network_edges.prices.setdefault(str(pool_asset).upper(), float(entry))
    caplog.clear()
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    assert not [r for r in caplog.records if "db_admission_timeout" in r.getMessage()]
    async with get_session() as session:
        rows = (await session.execute(select(Signal.asset, SignalDelivery.delivery_state)
                                      .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
                                      .join(User, User.id == SignalDelivery.user_id)
                                      .where(User.telegram_user_id == telegram_id, SignalDelivery.sent_ok.is_(True)))).all()
    assert len(rows) == 1 and str(rows[0][1]).lower() in {"sent", "confirmed", "delivered"}, rows
    assert any(m["chat_id"] == telegram_id and str(rows[0][0]) in m["text"] for m in network_edges.telegram.sent)


@pytest.mark.asyncio
async def test_the_background_scan_tracks_a_delivered_signal(postgres_database, network_edges):  # noqa: F811
    """The worker's active scan (not only the interactive reconcile) finds and advances it."""
    import signalrank_telegram.bot as bot
    from db.models import SignalLifecycle
    from db.session import get_session
    from engine.realtime_outcome_tracker import outcome_tracker

    telegram_id = await _vip_user()
    asset = f"B{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    stored = await _stored(_signal(asset))
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    await outcome_tracker._check_all()
    network_edges.prices[asset] = 102.05
    await outcome_tracker._check_all()
    async with get_session() as session:
        lifecycle = (await session.execute(select(SignalLifecycle)
                                           .where(SignalLifecycle.signal_id == stored["signal_id"]))).scalar_one()
    assert lifecycle.entry_touched_at is not None and lifecycle.tp1_hit_at is not None, lifecycle.state


@pytest.mark.asyncio
async def test_an_untouched_entry_expires_as_missed_and_is_not_a_loss(postgres_database, network_edges):  # noqa: F811
    from datetime import timedelta

    from sqlalchemy import update

    import signalrank_telegram.bot as bot
    from db.models import Outcome, Signal
    from db.session import get_session
    from engine.realtime_outcome_tracker import reconcile_signal_now

    telegram_id = await _vip_user()
    asset = f"M{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    stored = await _stored(_signal(asset))
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    network_edges.prices[asset] = 103.5  # ran away from a long entry at 100 without touching it
    past = datetime.now(timezone.utc).replace(tzinfo=None)
    async with get_session() as session:  # time passes: the entry window closes
        await session.execute(update(Signal).where(Signal.signal_id == stored["signal_id"])
                              .values(created_at=past - timedelta(hours=3), expires_at=past - timedelta(minutes=1)))
        await session.commit()
    await reconcile_signal_now(stored["signal_id"])
    await reconcile_signal_now(stored["signal_id"])
    async with get_session() as session:
        outcome = (await session.execute(select(Outcome).where(Outcome.signal_id == stored["signal_id"]))).scalar_one()
    assert str(outcome.status).lower() in {"missed_entry", "expired"}, outcome.status
    assert outcome.r_multiple is None  # never a realized loss or win
