import asyncio
import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis

    def set(self, *args, **kwargs):
        self.redis.set(*args, **kwargs)
        return self

    def sadd(self, *args, **kwargs):
        self.redis.sadd(*args, **kwargs)
        return self

    def expire(self, *_args, **_kwargs):
        return self

    def delete(self, *args, **kwargs):
        self.redis.delete(*args, **kwargs)
        return self

    def srem(self, *args, **kwargs):
        self.redis.srem(*args, **kwargs)
        return self

    def execute(self):
        return []


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}

    def pipeline(self, **_kwargs):
        return _FakePipeline(self)

    def set(self, key, value, **_kwargs):
        self.values[str(key)] = value

    def get(self, key):
        return self.values.get(str(key))

    def delete(self, key):
        self.values.pop(str(key), None)

    def sadd(self, key, value):
        self.sets.setdefault(str(key), set()).add(str(value))

    def smembers(self, key):
        return set(self.sets.get(str(key), set()))

    def srem(self, key, value):
        self.sets.setdefault(str(key), set()).discard(str(value))


class _FakeRedisState:
    def __init__(self):
        self.redis = _FakeRedis()

    def _get_redis_sync(self):
        return self.redis


def test_channel_scoped_idempotency_key_uses_exact_contract():
    from delivery.service import DeliveryOperation

    operation = DeliveryOperation(
        user_id=42,
        signal_id="sig-1",
        channel_id=-100123,
        signal_version="7",
        delivery_kind="signal",
    )
    expected = hashlib.sha256(b"42|sig-1|-100123|7|signal").hexdigest()

    assert operation.idempotency_key == expected
    assert DeliveryOperation(42, "sig-1", -100124, "7", "signal").idempotency_key != expected
    assert DeliveryOperation(42, "sig-1", -100123, "8", "signal").idempotency_key != expected


def test_delivery_state_is_monotonic_and_transmission_is_not_blindly_retried():
    from delivery.service import (
        DeliveryState,
        forbids_blind_retry,
        transition_allowed,
    )

    assert transition_allowed(DeliveryState.RESERVED, DeliveryState.VALIDATING)
    assert transition_allowed(DeliveryState.VALIDATING, DeliveryState.SENDING)
    assert transition_allowed(DeliveryState.SENDING, DeliveryState.CONFIRMED, proof_ok=True)
    assert not transition_allowed(DeliveryState.CONFIRMED, DeliveryState.FAILED_PRE_SEND)
    assert not transition_allowed(DeliveryState.AMBIGUOUS, DeliveryState.FAILED_PRE_SEND)
    assert forbids_blind_retry(DeliveryState.SENDING)
    assert forbids_blind_retry(DeliveryState.AMBIGUOUS)
    assert not forbids_blind_retry(DeliveryState.FAILED_PRE_SEND)


@pytest.mark.asyncio
async def test_receipt_stash_round_trip_and_acknowledgement():
    from delivery.receipts import DeliveryReceipt, ReceiptStore
    from delivery.service import DeliveryOperation

    store = ReceiptStore(_FakeRedisState())
    receipt = DeliveryReceipt.accepted(
        DeliveryOperation(42, "sig-2", 42),
        message_id=777,
        mode="sent",
    )

    assert await store.stash(receipt) is True
    assert await store.pending(limit=10) == [receipt]
    assert await store.acknowledge(receipt) is True
    assert await store.pending(limit=10) == []


@pytest.mark.asyncio
async def test_telegram_timeout_is_ambiguous_and_never_retried(monkeypatch):
    import signalrank_telegram.bot as bot_module
    from delivery.service import TelegramDeliveryAmbiguous

    attempts = 0

    async def _timeout(**_kwargs):
        nonlocal attempts
        attempts += 1
        raise asyncio.TimeoutError

    monkeypatch.setenv("TELEGRAM_SEND_MAX_ATTEMPTS", "5")
    bot = SimpleNamespace(send_message=_timeout)

    with pytest.raises(TelegramDeliveryAmbiguous):
        await bot_module._telegram_send_message_guarded(
            bot,
            chat_id=42,
            text="signal",
            parse_mode="HTML",
        )

    assert attempts == 1


@pytest.mark.asyncio
async def test_delivery_boundary_timeout_leaves_sending_state_without_second_send(monkeypatch):
    import engine.delivery_freshness as freshness_module
    import signalrank_telegram.bot as bot_module
    from delivery.service import TelegramDeliveryAmbiguous

    phases = []
    attempts = 0

    async def _phase(**kwargs):
        phases.append(kwargs["delivery_state"])
        return True

    async def _fresh(*_args, **_kwargs):
        return SimpleNamespace(ok=True, live_price=None, opportunity_remaining_pct=100.0)

    async def _none(*_args, **_kwargs):
        return None

    async def _unlocked(*_args, **_kwargs):
        return False

    async def _send(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise asyncio.TimeoutError

    monkeypatch.setattr(bot_module, "_persist_delivery_phase", _phase)
    monkeypatch.setattr(freshness_module, "validate_delivery_freshness", _fresh)
    monkeypatch.setattr(bot_module, "format_signal", lambda *_args, **_kwargs: "signal")
    monkeypatch.setattr(bot_module, "_find_editable_signal_message", _none)
    monkeypatch.setattr(bot_module, "_is_asset_delivery_locked", _unlocked)
    monkeypatch.setattr(bot_module, "_send_signal_with_engagement_async", _send)

    with pytest.raises(TelegramDeliveryAmbiguous):
        await bot_module._deliver_or_update_signal_async(
            bot=SimpleNamespace(),
            telegram_user_id=42,
            signal={"signal_id": "sig-3", "asset": "BTCUSDT", "timeframe": "5m"},
            display_tier="premium",
        )

    assert phases == ["VALIDATING", "SENDING"]
    assert attempts == 1


@pytest.mark.asyncio
async def test_late_failure_cannot_overwrite_confirmed_database_proof():
    from db.pg_features import mark_signal_delivery_result

    row = SimpleNamespace(
        sent_ok=True,
        delivery_state="CONFIRMED",
        telegram_chat_id=42,
        telegram_message_id=99,
        last_error=None,
    )

    class _Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class _Session:
        def __init__(self):
            self.results = iter((_Result(SimpleNamespace(id=5)), _Result(row)))
            self.flushed = False

        async def execute(self, _query):
            return next(self.results)

        async def flush(self):
            self.flushed = True

    session = _Session()
    assert await mark_signal_delivery_result(
        session,
        telegram_user_id=42,
        signal_id="sig-4",
        sent_ok=False,
        error="late_worker_failure",
        delivery_state="FAILED_PRE_SEND",
    ) is True

    assert row.sent_ok is True
    assert row.delivery_state == "CONFIRMED"
    assert row.telegram_message_id == 99
    assert session.flushed is False


@pytest.mark.asyncio
async def test_confirmation_atomically_saves_active_message_pointer():
    from db.models import ActiveSignalMessage
    from db.pg_features import mark_signal_delivery_result

    user = SimpleNamespace(id=5, timezone="UTC", telegram_user_id=42)
    row = SimpleNamespace(
        sent_ok=False,
        delivery_state="SENDING",
        telegram_chat_id=None,
        telegram_message_id=None,
        telegram_api_result={"idempotency_key": "stable"},
        telegram_send_started_at=None,
        attempt_count=1,
        last_error=None,
    )
    signal = SimpleNamespace(created_at=None)

    class _Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class _Session:
        def __init__(self):
            self.results = iter((_Result(user), _Result(row), _Result(signal), _Result(None)))
            self.added = []
            self.flushed = False

        async def execute(self, _query):
            return next(self.results)

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            self.flushed = True

    session = _Session()
    assert await mark_signal_delivery_result(
        session,
        telegram_user_id=42,
        signal_id="sig-active",
        sent_ok=True,
        telegram_chat_id=42,
        telegram_message_id=808,
        telegram_api_result={"mode": "sent"},
        delivery_state="CONFIRMED",
    ) is True

    assert row.sent_ok is True
    assert row.delivery_state == "CONFIRMED"
    assert row.telegram_api_result["idempotency_key"] == "stable"
    assert len(session.added) == 1
    active = session.added[0]
    assert isinstance(active, ActiveSignalMessage)
    assert (active.user_id, active.signal_id, active.chat_id, active.message_id) == (
        5,
        "sig-active",
        42,
        808,
    )
    assert session.flushed is True


@pytest.mark.asyncio
async def test_accepted_send_survives_db_failure_and_reconciles(monkeypatch):
    import db.pg_features as pg_features
    import db.session as db_session
    import delivery.receipts as receipts_module
    import delivery.worker as worker
    import signalrank_telegram.bot as bot_module
    from delivery.receipts import DeliveryReceipt, ReceiptStore
    from delivery.service import DeliveryOperation

    store = ReceiptStore(_FakeRedisState())
    receipt = DeliveryReceipt.accepted(
        DeliveryOperation(42, "sig-5", 42),
        message_id=1234,
        mode="sent",
    )
    assert await store.stash(receipt)
    proof = {
        "mode": "sent",
        "chat_id": 42,
        "message_id": 1234,
        "delivery_receipt": receipt.as_dict(),
        "receipt_stashed": True,
    }

    class _Session:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    @asynccontextmanager
    async def _session(**_kwargs):
        yield _Session()

    async def _db_down(*_args, **_kwargs):
        raise RuntimeError("injected proof write failure")

    monkeypatch.setattr(db_session, "get_session", _session)
    monkeypatch.setattr(pg_features, "mark_signal_delivery_result", _db_down)
    monkeypatch.setattr(receipts_module, "receipt_store", store)

    assert await bot_module._mark_delivery_with_telegram_proof(
        telegram_user_id=42,
        signal_id="sig-5",
        proof=proof,
        delivery_state="sent",
    ) is False
    assert await store.pending(limit=10) == [receipt]

    calls = []

    async def _db_recovered(*_args, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(pg_features, "mark_signal_delivery_result", _db_recovered)
    assert await worker.reconcile_delivery_receipt(receipt, store=store) is True
    assert calls[0]["delivery_state"] == "RECONCILED"
    assert calls[0]["sent_ok"] is True
    assert await store.pending(limit=10) == []
