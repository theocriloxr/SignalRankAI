from __future__ import annotations

import inspect
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.signal_lifecycle import (
    ACTIVE_TRADE,
    BREAKEVEN_STOP,
    EXPIRED,
    MISSED_ENTRY,
    SL_HIT,
    TP1_HIT,
    TP2_HIT,
    TP3_HIT,
    WATCHING_FOR_ENTRY,
    lifecycle_transition_allowed,
    normalize_lifecycle_state,
    outcome_transition_allowed,
)
from engine.outcome_snapshots import (
    SNAPSHOT_VERSION,
    build_outcome_snapshot,
    format_outcome_snapshot,
    read_cached_outcome_snapshot,
    write_outcome_snapshot,
)
from engine.realtime_outcome_tracker import (
    OutcomePriceObservation,
    RealtimeOutcomeTracker,
    _fetch_outcome_quotes,
    _get_outcome_quote,
)


def _signal(**overrides):
    payload = {
        "signal_id": "00000000-0000-0000-0000-000000000123",
        "asset": "BTCUSDT",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": [101.0, 102.0, 103.0],
        "timeframe": "1h",
        "lifecycle_state": ACTIVE_TRADE,
        "highest_tp_hit": 0,
        "prev_outcome_meta": {},
    }
    payload.update(overrides)
    return payload


def _observation(price: float | None, *, trusted: bool = True):
    return OutcomePriceObservation(
        asset="BTCUSDT",
        price=price,
        provider="test_provider",
        quote_time="2026-07-18T10:00:00+00:00" if price is not None else None,
        provider_trusted=trusted,
        reason=None if trusted else "provider_outage",
        request_id="quote-1",
    )


def test_canonical_lifecycle_normalizes_all_legacy_vocabularies():
    assert normalize_lifecycle_state("new") == WATCHING_FOR_ENTRY
    assert normalize_lifecycle_state("entry_hit") == ACTIVE_TRADE
    assert normalize_lifecycle_state("tp1") == TP1_HIT
    assert normalize_lifecycle_state("tp2_hit") == TP2_HIT
    assert normalize_lifecycle_state("tp") == TP3_HIT
    assert normalize_lifecycle_state("sl") == SL_HIT
    assert normalize_lifecycle_state("partial_win_be") == BREAKEVEN_STOP
    assert normalize_lifecycle_state("missed") == MISSED_ENTRY
    assert normalize_lifecycle_state("time_stop") == EXPIRED


def test_lifecycle_graph_allows_forward_progress_and_blocks_downgrade():
    assert lifecycle_transition_allowed(WATCHING_FOR_ENTRY, ACTIVE_TRADE)
    assert lifecycle_transition_allowed(ACTIVE_TRADE, TP1_HIT)
    assert lifecycle_transition_allowed(TP1_HIT, TP2_HIT)
    assert lifecycle_transition_allowed(TP2_HIT, TP3_HIT)
    assert not lifecycle_transition_allowed(TP2_HIT, TP1_HIT)
    assert not lifecycle_transition_allowed(TP3_HIT, SL_HIT)
    assert not lifecycle_transition_allowed(SL_HIT, ACTIVE_TRADE)


def test_outcome_projection_accepts_replay_but_rejects_reordering():
    assert outcome_transition_allowed("tp1", "tp1")
    assert outcome_transition_allowed("tp1", "tp2")
    assert outcome_transition_allowed("tp2", "partial_win_be")
    assert not outcome_transition_allowed("tp2", "tp1")
    assert not outcome_transition_allowed("tp3", "sl")
    assert not outcome_transition_allowed("sl", "tp1")


def test_transition_service_locks_before_monotonic_event_commit():
    from engine.signal_lifecycle import record_lifecycle_event

    source = inspect.getsource(record_lifecycle_event)
    assert ".with_for_update()" in source
    assert "event_transition_allowed(lifecycle.state, event_type)" in source
    assert "dispatch_event_notifications(" not in source


@pytest.mark.asyncio
async def test_quote_batch_fetches_each_unique_asset_once(monkeypatch):
    calls: list[str] = []

    async def fake_quote(asset: str):
        calls.append(asset)
        return OutcomePriceObservation(asset, 100.0, "fake", "now", True)

    monkeypatch.setattr("engine.realtime_outcome_tracker._get_outcome_quote", fake_quote)
    quotes = await _fetch_outcome_quotes(
        [
            _signal(signal_id="one", asset="btcusdt"),
            _signal(signal_id="two", asset="BTCUSDT"),
            _signal(signal_id="three", asset="ETHUSDT"),
        ]
    )

    assert sorted(calls) == ["BTCUSDT", "ETHUSDT"]
    assert set(quotes) == {"BTCUSDT", "ETHUSDT"}


@pytest.mark.asyncio
async def test_typed_quote_rejects_stale_provider_observation(monkeypatch):
    from data.provider_types import (
        BreakerState,
        LivePriceQuote,
        ProviderHealthState,
        QuoteKind,
    )

    now = time.time()
    stale_quote = LivePriceQuote(
        symbol="BTCUSDT",
        price=100.0,
        provider="fake",
        fetched_at=now,
        latency_ms=1,
        asset_class="crypto",
        source_timestamp=now - 3600,
        provider_health=ProviderHealthState.HEALTHY.value,
        breaker_state=BreakerState.CLOSED.value,
        quote_kind=QuoteKind.TRADE.value,
    )
    monkeypatch.setattr(
        "data.get_live_price.get_live_price_result",
        AsyncMock(return_value=stale_quote),
    )

    observation = await _get_outcome_quote("BTCUSDT")

    assert observation.price is None
    assert observation.provider_trusted is False
    assert "source_age_exceeded" in str(observation.reason)


@pytest.mark.asyncio
async def test_provider_outage_does_not_mutate_lifecycle_or_outcome(monkeypatch):
    lifecycle_update = AsyncMock()
    lifecycle_event = AsyncMock()
    persist = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr("engine.signal_lifecycle.update_lifecycle_observation", lifecycle_update)
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", lifecycle_event)
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", publish)

    await RealtimeOutcomeTracker()._check_signal(
        _signal(),
        observation=_observation(None, trusted=False),
    )

    lifecycle_update.assert_not_awaited()
    lifecycle_event.assert_not_awaited()
    persist.assert_not_awaited()
    publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_quote_can_advance_tp1_tp2_tp3_in_ledger_order(monkeypatch):
    events: list[str] = []
    statuses: list[str] = []

    async def record(_signal_row, event_type, _price, _meta=None):
        events.append(event_type)
        return True

    async def persist(_signal_id, status, _entry, _price):
        statuses.append(status)

    monkeypatch.setattr(
        "engine.signal_lifecycle.update_lifecycle_observation",
        AsyncMock(return_value=ACTIVE_TRADE),
    )
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", record)
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._set_tp_progress", AsyncMock())
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", AsyncMock())

    await RealtimeOutcomeTracker()._check_signal(
        _signal(),
        observation=_observation(104.0),
    )

    assert events == ["tp1_hit", "tp2_hit", "tp3_hit"]
    assert statuses == ["tp1", "tp2", "tp3"]


@pytest.mark.asyncio
async def test_replayed_lower_tp_does_not_downgrade_or_repersist(monkeypatch):
    lifecycle_event = AsyncMock()
    persist = AsyncMock()
    monkeypatch.setattr(
        "engine.signal_lifecycle.update_lifecycle_observation",
        AsyncMock(return_value=TP2_HIT),
    )
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", lifecycle_event)
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", AsyncMock())

    await RealtimeOutcomeTracker()._check_signal(
        _signal(
            lifecycle_state=TP2_HIT,
            highest_tp_hit=2,
            prev_outcome_status="tp2",
            prev_outcome_meta={"tp_hit_index": 2},
        ),
        observation=_observation(101.5),
    )

    lifecycle_event.assert_not_awaited()
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_lifecycle_replay_repairs_lagging_outcome_projection(monkeypatch):
    lifecycle_event = AsyncMock()
    persist = AsyncMock()
    monkeypatch.setattr(
        "engine.signal_lifecycle.update_lifecycle_observation",
        AsyncMock(return_value=TP2_HIT),
    )
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", lifecycle_event)
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", AsyncMock())

    await RealtimeOutcomeTracker()._check_signal(
        _signal(
            lifecycle_state=TP2_HIT,
            lifecycle_last_price=102.0,
            highest_tp_hit=2,
            prev_outcome_status="tp1",
            prev_outcome_meta={"tp_hit_index": 1},
        ),
        observation=_observation(101.5),
    )

    lifecycle_event.assert_not_awaited()
    persist.assert_awaited_once_with(
        "00000000-0000-0000-0000-000000000123",
        "tp2",
        100.0,
        102.0,
    )


@pytest.mark.asyncio
async def test_versioned_snapshot_round_trip_and_next_target(monkeypatch):
    cache: dict[str, str] = {}
    ttl_seen: list[int] = []

    async def cache_set(key, value, *, ex=None):
        cache[key] = value
        ttl_seen.append(int(ex or 0))

    async def cache_get(key):
        return cache.get(key)

    monkeypatch.setattr("core.redis_state.state.cache_set", cache_set)
    monkeypatch.setattr("core.redis_state.state.cache_get", cache_get)
    snapshot = build_outcome_snapshot(
        _signal(),
        state=TP1_HIT,
        highest_tp_hit=1,
        price=101.25,
        quote_time="2026-07-18T10:00:00+00:00",
        provider="test_provider",
        provider_trusted=True,
    )

    assert await write_outcome_snapshot(snapshot)
    restored = await read_cached_outcome_snapshot(snapshot.signal_id)

    assert restored is not None
    assert restored.version == SNAPSHOT_VERSION
    assert restored.state == TP1_HIT
    assert restored.highest_tp_hit == 1
    assert restored.next_target == 102.0
    assert ttl_seen and ttl_seen[0] >= 30


@pytest.mark.asyncio
async def test_check_outcome_callback_uses_snapshot_before_database(monkeypatch):
    from signalrank_telegram.callback_handlers import _handle_check_outcome

    snapshot = build_outcome_snapshot(
        _signal(),
        state=TP2_HIT,
        highest_tp_hit=2,
        price=102.25,
        quote_time="2026-07-18T10:00:00+00:00",
        provider="test_provider",
        provider_trusted=True,
    )
    snapshot_read = AsyncMock(return_value=snapshot)
    monkeypatch.setattr("engine.outcome_snapshots.read_cached_outcome_snapshot", snapshot_read)

    def database_must_not_open(*_args, **_kwargs):
        raise AssertionError("snapshot hit must bypass database fallback")

    monkeypatch.setattr("db.session.get_session", database_must_not_open)
    query = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(chat_id=99),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=bot)

    await _handle_check_outcome(update, context, snapshot.signal_id)

    snapshot_read.assert_awaited_once_with(snapshot.signal_id)
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == format_outcome_snapshot(snapshot)
    assert bot.send_message.await_args.kwargs["parse_mode"] == "HTML"
