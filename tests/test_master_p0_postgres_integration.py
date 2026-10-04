"""Real PostgreSQL regression flows; hermetic/mock results cannot satisfy these."""
import asyncio
from datetime import datetime, timedelta
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.engine import make_url


@pytest.mark.asyncio
@pytest.mark.parametrize("status,eligible", [
    (None, True), ("pending", True), ("tp1", True), ("tp2", True),
    ("tp3", False), ("sl", False), ("stop", False), ("stopped", False),
    ("partial_win", False), ("partial_win_be", False), ("breakeven", False),
    ("be", False), ("missed", False), ("expired", False), ("cancelled", False),
    ("closed", False), (" PARTIAL-WIN-BE ", False), ("\tSL\n", False),
])
async def test_available_signal_query_preserves_terminal_policy_in_postgres(postgres_database, status, eligible):
    from db.models import User, Signal, Outcome
    from db.pg_features import _available_signal_query
    from db.session import get_session
    now, signal_id = datetime.utcnow(), str(uuid4())
    async with get_session() as session:
        user = User(username="available-" + uuid4().hex[:16], tier="free")
        signal = Signal(signal_id=signal_id, asset="AUDITAVAILABLE", direction="long", timeframe="1h",
                        entry=100, stop_loss=99, take_profit="[101]", score=90,
                        strategy_name="audit", strategy_group="audit", strength=1, created_at=now)
        session.add_all([user, signal])
        await session.flush()
        if status is not None:
            session.add(Outcome(signal_id=signal_id, status=status, meta={}))
            await session.flush()
        for ranked in (False, True):
            query = _available_signal_query(user_id=user.id, cutoff=now - timedelta(minutes=1),
                                            locked_assets=set(), min_score=80, ranked=ranked)
            rows = list((await session.execute(query.where(Signal.signal_id == signal_id))).scalars().all())
            assert bool(rows) is eligible
        await session.rollback()


@pytest.mark.asyncio
async def test_available_signal_query_excludes_unavailable_and_other_user_delivery_is_scoped(postgres_database):
    from db.models import User, Signal, SignalDelivery
    from db.pg_features import _available_signal_query
    from db.session import get_session
    now = datetime.utcnow()
    async with get_session() as session:
        users = [User(username="available-" + uuid4().hex[:16], tier="free") for _ in range(2)]
        session.add_all(users)
        signals = {}
        for name in ("eligible", "delivered", "other_user", "archived", "expired", "old", "low_score", "asset_locked"):
            signal = Signal(signal_id=str(uuid4()), asset=" lockedasset " if name == "asset_locked" else "AUDITAVAILABLE",
                            direction="long", timeframe="1h", entry=100, stop_loss=99, take_profit="[101]",
                            score=79 if name == "low_score" else 90, strategy_name="audit", strategy_group="audit",
                            strength=1, created_at=now - timedelta(days=2) if name == "old" else now,
                            archived=name == "archived", expired=name == "expired")
            signals[name] = signal
            session.add(signal)
        await session.flush()
        session.add_all([
            SignalDelivery(user_id=users[0].id, signal_id=signals["delivered"].signal_id, sent_ok=False),
            SignalDelivery(user_id=users[1].id, signal_id=signals["other_user"].signal_id, sent_ok=True),
        ])
        await session.flush()
        query = _available_signal_query(user_id=users[0].id, cutoff=now - timedelta(days=1),
                                        locked_assets={"LOCKEDASSET"}, min_score=80)
        rows = list((await session.execute(query.where(Signal.signal_id.in_([s.signal_id for s in signals.values()])))).scalars().all())
        assert {row.signal_id for row in rows} == {signals["eligible"].signal_id, signals["other_user"].signal_id}
        await session.rollback()


@pytest.mark.asyncio
async def test_available_signal_query_bounds_results_and_preserves_ranking_in_postgres(postgres_database):
    from db.models import User, Signal
    from db.pg_features import _available_signal_query
    from db.session import get_session
    now = datetime.utcnow()
    async with get_session() as session:
        user = User(username="available-" + uuid4().hex[:16], tier="free")
        session.add(user)
        signals = [Signal(signal_id=str(uuid4()), asset="AUDITAVAILABLE", direction="long", timeframe="1h",
                          entry=100, stop_loss=99, take_profit="[101]", score=80 + i % 20,
                          strategy_name="audit", strategy_group="audit", strength=1,
                          created_at=now - timedelta(seconds=i)) for i in range(270)]
        session.add_all(signals)
        await session.flush()
        ids = [signal.signal_id for signal in signals]
        recent = _available_signal_query(user_id=user.id, cutoff=now - timedelta(hours=1), locked_assets=set())
        rows = list((await session.execute(recent.where(Signal.signal_id.in_(ids)))).scalars().all())
        assert len(rows) == 250 and [row.signal_id for row in rows] == ids[:250]
        ranked = _available_signal_query(user_id=user.id, cutoff=now - timedelta(hours=1), locked_assets=set(), ranked=True)
        rows = list((await session.execute(ranked.where(Signal.signal_id.in_(ids)))).scalars().all())
        expected = sorted(signals, key=lambda signal: (-signal.score, -signal.created_at.timestamp(), signal.signal_id))[:100]
        assert len(rows) == 100 and [row.signal_id for row in rows] == [signal.signal_id for signal in expected]
        await session.rollback()


@pytest.mark.asyncio
async def test_dedup_queries_actual_postgres_and_canonical_side_aliases(postgres_database):
    from db.models import Signal
    from db.session import get_session
    from engine.signal_deduplicator import SignalDeduplicator
    from engine.signal_dedup_strict import StrictSignalDedup
    asset = "AUDIT" + uuid4().hex[:12].upper()
    dedup = SignalDeduplicator()
    assert not await dedup.is_duplicate(asset, "1h", "BUY", 100)
    async with get_session() as session:
        session.add(Signal(signal_id=str(uuid4()), asset=asset, direction="BUY", timeframe="1h",
                           entry=100, stop_loss=99, take_profit="[101]", score=90,
                           strategy_name="audit", strategy_group="audit", strength=1))
        await session.commit()
    assert await dedup.is_duplicate(asset, "1h", "BUY", 100)
    assert not await dedup.is_duplicate(asset, "1h", "SELL", 100)
    history = await dedup.get_recent_signals(asset, "1h", "long")
    assert len(history) == 1 and history[0]["asset"] == asset
    assert len(await dedup.get_recent_signals(asset, "1h", "BUY")) == 1
    duplicates = await dedup.find_semantic_duplicates({"asset": asset, "timeframe": "1h", "direction": "long", "entry": 100})
    assert len(duplicates) == 1 and duplicates[0][1] > 0.9
    strict = StrictSignalDedup()
    assert (await strict.is_duplicate_strict(asset, "1h", "long"))[0]
    assert len(await strict.find_duplicates_strict(asset, "1h", "BUY")) == 1


@pytest.mark.asyncio
async def test_performance_queries_use_signal_regime_and_asset_class(postgres_database):
    from db.models import Signal, Outcome
    from db.pg_features import get_strategy_performance_by_regime, get_asset_class_strategy_performance
    from db.session import get_session
    marker = uuid4().hex[:20]
    async with get_session() as session:
        for asset_class, status, percent in (("crypto", "win", 2.5), ("forex", "loss", -0.5)):
            signal_id = str(uuid4())
            session.add(Signal(signal_id=signal_id, asset="AUDITPERF", direction="long", timeframe="1h",
                               entry=100, stop_loss=99, take_profit="[101]", score=90,
                               strategy_name=marker, strategy_group="audit", strength=1,
                               regime=marker, asset_class=asset_class))
            await session.flush()
            session.add(Outcome(signal_id=signal_id, status=status, pnl_pct=percent, meta={}))
        await session.flush()
        overall = await get_strategy_performance_by_regime(session, marker, marker)
        crypto = await get_asset_class_strategy_performance(session, marker, "crypto", marker)
        assert overall["trades"] == 2 and overall["win_rate"] == 0.5 and overall["avg_rr"] == 5
        assert crypto["trades"] == 1 and crypto["win_rate"] == 1
        assert (await get_strategy_performance_by_regime(session, marker, "missing"))["trades"] == 0
        await session.rollback()


@pytest.mark.asyncio
async def test_web_only_referrers_have_separate_reward_identities(postgres_database, monkeypatch):
    from db.models import User, ReferralReward
    from db.pg_features import get_or_create_referral_code_for_user, process_referral_start
    from db.session import get_session
    monkeypatch.setenv("REFERRALS_PER_REWARD", "1")
    monkeypatch.setenv("REFERRAL_BONUS_DAYS", "7")
    marker = uuid4().hex
    async with get_session() as session:
        owners = [User(username=f"audit-{marker[:16]}-{i}", telegram_user_id=None, tier="free") for i in range(2)]
        session.add_all(owners)
        await session.flush()
        for i, owner in enumerate(owners):
            code = await get_or_create_referral_code_for_user(session, referrer_user_id=owner.id)
            referred_id = 8000000000 + int(uuid4().hex[:8], 16)
            result = await process_referral_start(session, referred_id, code, True)
            assert result["status"] == "reward_granted" and result["days_granted"] == 7
            assert result["referrer_id"] is None
            duplicate = await process_referral_start(session, referred_id, code, True)
            assert duplicate["status"] == "already_referred" and duplicate["referrer_id"] is None
        rewards = list((await session.execute(select(ReferralReward).where(
            ReferralReward.referrer_user_id.in_([owner.id for owner in owners]), ReferralReward.reward_type == "premium_days",
        ))).scalars().all())
        assert len(rewards) == 2 and len({reward.reference for reward in rewards}) == 2
        assert {reward.reference for reward in rewards} == {f"REFERRAL:USER:{owner.id}:1" for owner in owners}
        await session.rollback()


@pytest.mark.asyncio
async def test_web_only_users_are_excluded_from_telegram_queues(postgres_database):
    from db.models import User, Signal, FreeSignalQueue
    from db.pg_features import get_due_free_signal_summaries, list_all_user_telegram_ids
    from db.session import get_session
    now = datetime.utcnow()
    marker, signal_id = uuid4().hex, str(uuid4())
    telegram_id = 8000000000 + int(uuid4().hex[:8], 16)
    async with get_session() as session:
        web_user = User(username=f"web-{marker[:16]}", telegram_user_id=None, tier="free")
        telegram_user = User(telegram_user_id=telegram_id, tier="free")
        session.add_all([web_user, telegram_user])
        session.add(Signal(signal_id=signal_id, asset="AUDITQUEUE", direction="long", timeframe="1h",
                           entry=100, stop_loss=99, take_profit="[101]", score=90,
                           strategy_name="audit", strategy_group="audit", strength=1))
        await session.flush()
        session.add(FreeSignalQueue(user_id=web_user.id, signal_id=signal_id, date=now, asset="AUDITQUEUE",
                                    direction="long", timeframe="1h", score=90, queued_at=now,
                                    deliver_after=now - timedelta(seconds=1), status="queued"))
        await session.flush()
        summaries = await get_due_free_signal_summaries(session)
        assert all(item["signal_id"] != signal_id for items in summaries.values() for item in items)
        ids = await list_all_user_telegram_ids(session)
        assert telegram_id in ids and all(isinstance(value, int) for value in ids)
        await session.rollback()


@pytest_asyncio.fixture
async def postgres_database():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    required = os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1"
    if not url:
        if required:
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql", "SQLite cannot certify PostgreSQL flows"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}, "integration mutations require a local isolated database"
    assert "test" in (parsed.database or "") or parsed.database == "signalrank_master_audit"
    async with get_session() as session:
        from sqlalchemy import text
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0048_runtime_schema_bridge"
    yield
    await dispose_engine_for_event_loop()


@pytest.mark.asyncio
async def test_rejection_tracker_writes_jsonb_owner_of_computed_view(postgres_database, monkeypatch):
    from db.models import DecisionLog
    from db.session import get_session
    from engine.signal_deduplicator import MLRejectionTracker
    from sqlalchemy import delete, text

    monkeypatch.setenv("REJECT_OUTCOME_WINDOWS", "5m")
    async with get_session() as session:
        kind = (await session.execute(text("SELECT relkind FROM pg_class WHERE oid=to_regclass('public.ml_rejected_signals')"))).scalar_one()
        assert kind in {"v", b"v"}, "This regression requires the actual 0046 computed view"
        row = DecisionLog(asset="AUDIT_VIEW_WRITE", timeframe="5m", decision="rejected", reason="audit",
                          created_at=datetime.utcnow()-timedelta(hours=1),
                          meta={"layer":"ml", "features":{}, "direction":"LONG", "audit_marker":"preserve-me"})
        session.add(row)
        await session.flush()
        row_id = row.id
        await session.commit()
    tracker = MLRejectionTracker()
    async def noop(*args, **kwargs): return 0
    async def evaluate(**kwargs): return "win", {"source":"isolated-regression"}, 101.0
    monkeypatch.setattr(tracker, "flush_pending_rejections", noop)
    monkeypatch.setattr(tracker, "_evaluate_window", evaluate)
    monkeypatch.setattr(tracker, "_notify_rejection_outcomes", noop)
    monkeypatch.setattr(tracker, "_run_adaptive_learning_if_due", noop)
    try:
        assert await tracker.track_rejection_outcomes() >= 1
        async with get_session() as session:
            actual = await session.get(DecisionLog, row_id)
            assert actual.meta["audit_marker"] == "preserve-me"
            assert actual.meta["actual_outcome"] == "win"
            assert actual.meta["outcome_tracked_at"]
            assert actual.meta["features"]["outcome_labels"]["5m"] == "win"
    finally:
        async with get_session() as session:
            await session.execute(delete(DecisionLog).where(DecisionLog.id == row_id))
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("filtered", [False, True])
async def test_nullable_web_search_filters_execute_on_postgres(postgres_database, filtered):
    from web.platform_api import instrument_search, signal_feed

    user = {"id": 2147483647, "tier": "free"}
    feed = await signal_feed(
        limit=30, offset=0, asset="BTCUSDT" if filtered else None,
        asset_class="crypto" if filtered else None, timeframe="5m" if filtered else None,
        strategy="audit" if filtered else None, status="active" if filtered else None, user=user,
    )
    assert feed["signals"] == []
    assert feed["limit"] == 30
    instruments = await instrument_search(
        q="AUDIT_NO_MATCH_20261003" if filtered else "",
        asset_class="crypto" if filtered else None,
        instrument_type="spot" if filtered else None,
        venue="audit-no-match" if filtered else None, limit=30, user=user,
    )
    assert isinstance(instruments["instruments"], list)
    if filtered:
        assert instruments["instruments"] == []


@pytest.mark.asyncio
async def test_oct1_receipt_paper_idempotency_and_missed_entry_on_postgres(postgres_database):
    from scripts.staging_oct1_incident_replay import _run_replay

    result = await _run_replay({"environment": "test", "scope": "LOCAL_REAL_POSTGRES"})
    assert result["status"] == "PASS"
    assert result["external_notifications_sent"] is False
    assert result["broker_orders_submitted"] is False
    assert all(result["assertions"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("direction,quantity,fill,error", [
    ("long", 2.0, 100.0, None), ("short", 2.0, 100.0, None),
    ("sideways", 2.0, 100.0, "paper_position_direction_invalid"),
    ("long", 0.0, 100.0, "paper_position_geometry_invalid"),
    ("long", -2.0, 100.0, "paper_position_geometry_invalid"),
    ("long", float("inf"), 100.0, "paper_position_geometry_invalid"),
    ("long", 2.0, 0.0, "paper_position_geometry_invalid"),
    ("long", 2.0, float("nan"), "paper_position_geometry_invalid"),
])
async def test_paper_exit_ledger_rejects_bad_geometry_and_closes_once_on_postgres(
    postgres_database, direction, quantity, fill, error,
):
    from core.paper_trading_service import PaperTradingService
    from db.models import User, Signal, PaperAccount, PaperPosition, PaperLedgerEntry
    from db.session import get_session
    from sqlalchemy import delete
    signal_id, position_id = str(uuid4()), str(uuid4())
    async with get_session() as session:
        user = User(username="paper-boundary-" + uuid4().hex[:12], tier="vip")
        signal = Signal(signal_id=signal_id, asset="AUDITPAPER", direction="long", timeframe="1h",
                        entry=100, stop_loss=90, take_profit="[110]", score=90,
                        strategy_name="audit", strategy_group="audit", strength=1)
        session.add_all([user, signal])
        await session.flush()
        user_id = user.id
        account = PaperAccount(user_id=user_id, starting_balance=1000, cash_balance=800, fee_bps=0)
        session.add(account)
        await session.flush()
        account_id = account.id
        position = PaperPosition(position_id=position_id, account_id=account_id, user_id=user_id,
                                 signal_id=signal_id, asset="AUDITPAPER", direction=direction,
                                 signal_entry=100, fill_entry=fill, current_price=100, quantity=quantity,
                                 stop_loss=110 if direction == "short" else 90,
                                 target_price=90 if direction == "short" else 110,
                                 reserved_cash=200, notional=200, entry_fee=0)
        session.add(position)
        await session.commit()
    try:
        service = PaperTradingService()
        price = 90.0 if direction == "short" else 110.0
        if error:
            with pytest.raises(ValueError, match=error):
                await service._mark_one(position_id, price)
        else:
            assert await service._mark_one(position_id, price) is True
            assert await service._mark_one(position_id, price) is False
        async with get_session() as session:
            stored = (await session.execute(select(PaperPosition).where(PaperPosition.position_id == position_id))).scalar_one()
            balance = (await session.execute(select(PaperAccount.cash_balance).where(PaperAccount.id == account_id))).scalar_one()
            entries = (await session.execute(select(func.count(PaperLedgerEntry.id)).where(PaperLedgerEntry.position_id == position_id))).scalar_one()
            assert stored.status == ("open" if error else "closed")
            assert balance == (800 if error else 1020)
            assert entries == (0 if error else 1)
            assert stored.realized_pnl == (0 if error else 20)
    finally:
        async with get_session() as session:
            await session.execute(delete(PaperLedgerEntry).where(PaperLedgerEntry.position_id == position_id))
            await session.execute(delete(PaperPosition).where(PaperPosition.position_id == position_id))
            await session.execute(delete(PaperAccount).where(PaperAccount.id == account_id))
            await session.execute(delete(Signal).where(Signal.signal_id == signal_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()


@pytest.mark.asyncio
async def test_lifecycle_notification_materializes_plan_and_sends_once(postgres_database, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from config import config
    from db.models import Signal, SignalDelivery, SignalEventNotification, SignalTrackingEvent, User
    from db.session import get_session
    from engine.signal_lifecycle import dispatch_event_notifications

    signal_id = str(uuid4())
    telegram_id = 8000000000 + int(uuid4().hex[:8], 16)
    now = datetime.utcnow()
    plan = {"signal_id": signal_id, "asset": "US30", "timeframe": "15m", "direction": "SELL",
            "entry": 50686.17, "stop_loss": 50877.72, "take_profits": [50494.62, 50303.07, 50111.52]}
    mutable = {**plan, "entry": 51321.24, "stop_loss": 51484.8}
    async with get_session() as session:
        user = User(telegram_user_id=telegram_id, username="audit-notification", tier="vip", timezone="Africa/Lagos")
        session.add(user)
        session.add(Signal(signal_id=signal_id, asset="US30", direction="short", timeframe="15m",
                           entry=mutable["entry"], stop_loss=mutable["stop_loss"], take_profit=json.dumps(plan["take_profits"]),
                           score=90, strategy_name="audit", strategy_group="audit", strength=1, created_at=now))
        await session.flush()
        delivery = SignalDelivery(user_id=user.id, signal_id=signal_id, tier_at_send="vip", sent_ok=True,
                                  delivery_state="confirmed", telegram_chat_id=telegram_id, telegram_message_id=990005,
                                  delivery_confirmed_at=now, telegram_api_result={"ok": True, "signal_snapshot": plan})
        event = SignalTrackingEvent(signal_id=signal_id, event_type="entry_touched", event_time=now,
                                    price=plan["entry"], meta={})
        session.add_all([delivery, event])
        await session.flush()
        notification = SignalEventNotification(event_id=event.id, signal_id=signal_id, event_type="entry_touched",
                                              user_id=user.id, telegram_user_id=telegram_id, delivery_id=delivery.id,
                                              chat_id=telegram_id, source_message_id=990005)
        session.add(notification)
        await session.flush()
        event_id, notification_id = event.id, notification.id
        await session.commit()

    active_sessions = 0
    messages = []
    @asynccontextmanager
    async def scope(**kwargs):
        nonlocal active_sessions
        async with get_session(**kwargs) as session:
            active_sessions += 1
            try:
                yield session
            finally:
                active_sessions -= 1

    class Bot:
        def __init__(self, **kwargs):
            pass
        async def send_message(self, **kwargs):
            assert active_sessions == 0
            messages.append(kwargs)
            return SimpleNamespace(message_id=990006)

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "unit-test-placeholder")
    monkeypatch.setenv("LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED", "1")
    monkeypatch.setattr("db.session.get_session", scope)
    monkeypatch.setattr("telegram.Bot", Bot)
    await dispatch_event_notifications(event_id, mutable)
    await dispatch_event_notifications(event_id, mutable)
    assert len(messages) == 1
    assert messages[0]["chat_id"] == telegram_id
    assert "50,686.17" in messages[0]["text"]
    assert "Planned entry: <code>50,686.17</code>" in messages[0]["text"]
    assert "Planned stop: <code>50,877.72</code>" in messages[0]["text"]
    assert "51,321.24" not in messages[0]["text"]
    assert signal_id in messages[0]["text"]
    async with get_session() as session:
        persisted = await session.get(SignalEventNotification, notification_id)
        assert persisted.sent_ok
        assert persisted.sent_message_id == 990006


@pytest.mark.asyncio
async def test_concurrent_tp_writers_cannot_expire_or_duplicate_terminal_trade(postgres_database, monkeypatch):
    from db.models import Signal, SignalLifecycle, SignalTrackingEvent
    from db.session import get_session
    from engine.signal_lifecycle import record_lifecycle_event

    monkeypatch.setenv("OUTCOME_LIFECYCLE_ENABLED", "1")
    now = datetime.utcnow()
    signal_id = str(uuid4())
    plan = {"signal_id": signal_id, "asset": "JNJ", "entry": 262.2601, "stop_loss": 262.7518,
            "take_profit": [260.8439, 259.4277, 258.0116], "direction": "short",
            "created_at": now, "expires_at": now + timedelta(hours=1)}
    async with get_session() as session:
        session.add(Signal(signal_id=signal_id, asset="JNJ", timeframe="1m", direction="short",
                           entry=plan["entry"], stop_loss=plan["stop_loss"], take_profit=json.dumps(plan["take_profit"]),
                           score=90, strategy_name="audit", strategy_group="audit", strength=1,
                           created_at=now, expires_at=plan["expires_at"]))
        session.add(SignalLifecycle(signal_id=signal_id, state="ACTIVE_TRADE", entry_touched_at=now))
        await session.commit()
    from engine.signal_lifecycle import update_lifecycle_observation
    assert await update_lifecycle_observation({**plan, "direction": "SELL"}, 261.0) == "ACTIVE_TRADE"
    async with get_session() as session:
        observed = (await session.execute(select(SignalLifecycle).where(SignalLifecycle.signal_id == signal_id))).scalar_one()
        assert observed.mfe_r > 0
        assert observed.mae_r == 0
    results = await asyncio.gather(*[
        record_lifecycle_event(plan, "tp1_hit", 260.8439, {"observation_price": 260.8}) for _ in range(8)
    ])
    assert sum(results) == 1
    assert not await record_lifecycle_event(plan, "expired", 262.45)
    assert await record_lifecycle_event(plan, "time_stop", 262.45)
    assert not await record_lifecycle_event(plan, "time_stop", 262.45)
    async with get_session() as session:
        lifecycle = (await session.execute(select(SignalLifecycle).where(SignalLifecycle.signal_id == signal_id))).scalar_one()
        assert lifecycle.state == "CLOSED_TIME_STOP"
        count = (await session.execute(select(func.count()).select_from(SignalTrackingEvent).where(
            SignalTrackingEvent.signal_id == signal_id, SignalTrackingEvent.event_type == "tp1_hit"))).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_stale_outcome_writer_cannot_override_active_lifecycle(postgres_database):
    from db.models import Outcome, Signal, SignalLifecycle
    from db.session import get_session
    from engine.realtime_outcome_tracker import _persist_outcome

    signal_id = str(uuid4())
    async with get_session() as session:
        session.add(Signal(signal_id=signal_id, asset="AUDIT", timeframe="1m", direction="long", entry=100,
                           stop_loss=95, take_profit="[102,104,106]", score=90, strategy_name="audit",
                           strategy_group="audit", strength=1))
        session.add(SignalLifecycle(signal_id=signal_id, state="ACTIVE_TRADE", entry_touched_at=datetime.utcnow()))
        await session.commit()
    await _persist_outcome(signal_id, "expired", 100, 99)
    async with get_session() as session:
        assert (await session.execute(select(Outcome).where(Outcome.signal_id == signal_id))).scalar_one_or_none() is None
