from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.outcome_accounting import outcome_price_metrics
from core.signal_lifecycle import (
    ACTIVE_TRADE, CLOSED_TIME_STOP, EXPIRED, MISSED_ENTRY, TP1_HIT, TP2_HIT,
    WATCHING_FOR_ENTRY, event_transition_allowed, is_terminal_signal_state,
    outcome_status_for_lifecycle, normalize_lifecycle_state, outcome_transition_allowed,
)
from engine.signal_lifecycle import validate_lifecycle_price_evidence
from services.outcome_reconciliation import _projection_metrics


@pytest.mark.parametrize("state", [ACTIVE_TRADE, TP1_HIT, TP2_HIT])
def test_triggered_trade_cannot_expire_as_preentry(state):
    assert not event_transition_allowed(state, "expired")
    assert not event_transition_allowed(state, "missed_entry")
    assert event_transition_allowed(state, "time_stop")
    assert is_terminal_signal_state(CLOSED_TIME_STOP)
    assert outcome_status_for_lifecycle(CLOSED_TIME_STOP) == "time_stop"


def test_preentry_cannot_use_executed_time_stop():
    assert not event_transition_allowed(WATCHING_FOR_ENTRY, "time_stop")
    assert event_transition_allowed(WATCHING_FOR_ENTRY, "missed_entry")
    assert not event_transition_allowed(MISSED_ENTRY, "entry_touched")


def test_corrupt_lifecycle_and_unknown_events_cannot_reactivate_a_signal():
    with pytest.raises(ValueError, match="unknown_signal_lifecycle_state"):
        normalize_lifecycle_state("CORRUPT_TERMINAL")
    assert is_terminal_signal_state("CORRUPT_TERMINAL")
    assert not event_transition_allowed("CORRUPT_TERMINAL", "entry_touched")
    assert not event_transition_allowed(WATCHING_FOR_ENTRY, "unsupported_event")
    assert not outcome_transition_allowed("pending", "invented_profit")
    assert not outcome_transition_allowed("corrupt_outcome", "tp1")


def _jnj():
    return SimpleNamespace(entry=262.2601, stop_loss=262.7518, direction="short",
                           take_profit=[260.8439, 259.4277, 258.0116])


def test_jnj_rebound_cannot_be_converted_into_a_profitable_tp():
    with pytest.raises(ValueError, match="outcome_target_not_crossed"):
        outcome_price_metrics(_jnj(), "tp1", 262.45)
    with pytest.raises(ValueError, match="outcome_target_not_crossed"):
        _projection_metrics(_jnj(), SimpleNamespace(highest_tp_hit=1), "tp1", 262.45)
    r, pct = outcome_price_metrics(_jnj(), "tp1", 260.8439)
    assert r > 0 and pct == pytest.approx(0.54, abs=0.001)


def test_tp_event_requires_actual_crossing_even_if_event_price_is_target():
    with pytest.raises(ValueError, match="outcome_target_not_crossed"):
        validate_lifecycle_price_evidence(vars(_jnj()), "tp1_hit", 260.8439,
                                         {"observation_price": 262.45})
    validate_lifecycle_price_evidence(vars(_jnj()), "tp1_hit", 260.8439,
                                     {"observation_price": 262.45, "observation_low": 260.8})


@pytest.mark.parametrize("status", ["missed_entry", "expired"])
def test_bac_untriggered_expiry_never_books_counterfactual_loss(status):
    signal = SimpleNamespace(entry=50, stop_loss=51, direction="short")
    assert outcome_price_metrics(signal, status, 53.69) == (None, None)
    r, pct, _ = _projection_metrics(signal, SimpleNamespace(highest_tp_hit=0), status, 53.69)
    assert r is None and pct is None


def test_time_stop_preserves_signed_executed_loss():
    signal = SimpleNamespace(entry=50, stop_loss=55, direction="short")
    assert outcome_price_metrics(signal, "time_stop", 52) == (-0.4, -4.0)


def test_unknown_outcome_cannot_become_active_or_realized():
    from core.signal_lifecycle import lifecycle_state_for_outcome
    with pytest.raises(ValueError, match="outcome_status_unknown"):
        lifecycle_state_for_outcome("unknown-state")
    with pytest.raises(ValueError, match="outcome_status_unknown"):
        outcome_price_metrics(_jnj(), "unknown-state", 260)


def test_missing_model_prediction_is_not_synthesized_from_technical_scores():
    from engine.signal_metrics import resolve_ml_probability
    assert resolve_ml_probability({"score": 95, "confidence": 0.9, "confluence": 88}) is None
    assert resolve_ml_probability({"ml_probability": float("nan"), "score": 95}) is None
    assert resolve_ml_probability({"ml_probability": 120}) is None


def test_explanation_component_accepts_fraction_or_percent_without_inflation():
    from engine.signal_explainability import build_signal_explanation
    for value in (0.82, 82):
        explanation = build_signal_explanation({"score_components": {"confluence": value}})
        assert "Confluence component 82%" in explanation["drivers"]
        assert "8200%" not in str(explanation)


def test_snapshot_sell_alias_preserves_short_lifecycle_math():
    from engine.realtime_outcome_tracker import _delivery_snapshot_signature, _tracked_signal_payload
    from engine.signal_lifecycle import evaluate_observation
    signal = SimpleNamespace(signal_id="jnj-alias", **vars(_jnj()))
    snapshot = {"asset": "JNJ", "timeframe": "1m", **vars(_jnj()), "direction": "SELL"}
    payload = _tracked_signal_payload(signal, None, None, snapshot, reason="test")
    assert payload["direction"] == "short"
    assert _delivery_snapshot_signature(snapshot) == _delivery_snapshot_signature({**snapshot, "direction": "short"})
    assert evaluate_observation(state=ACTIVE_TRADE, direction="SELL", entry=262.2601, stop_loss=262.7518,
                                tp_levels=[260.8439], current_price=262.45) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("notification", ["_notify_risk_free_update", "_notify_retrace_warning"])
async def test_observation_notifications_release_db_before_network_and_require_receipts(monkeypatch, notification):
    from contextlib import asynccontextmanager
    import engine.realtime_outcome_tracker as tracker
    from config import config
    active = {"session": False}
    messages = []

    @asynccontextmanager
    async def scope(**_kwargs):
        active["session"] = True
        yield SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(1, "vip"), (1, "vip"), (2, "free")])))
        active["session"] = False

    def send(_bot, **kwargs):
        assert active["session"] is False
        messages.append(kwargs)

    monkeypatch.setattr("db.session.get_session", scope)
    monkeypatch.setattr("telegram.Bot", lambda **_kwargs: object())
    import sys
    from types import ModuleType
    bot_boundary = ModuleType("signalrank_telegram.bot")
    bot_boundary._send_message_sync = send
    monkeypatch.setitem(sys.modules, "signalrank_telegram.bot", bot_boundary)
    monkeypatch.setattr(tracker, "_mark_risk_free_recipient_triggered", AsyncMock(return_value=True))
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "unit-test-placeholder")
    signal = {"signal_id": "0140438f-a1bd-4eb4-bdb2-89e9256734c5", "asset": "JNJ", **vars(_jnj())}
    await getattr(tracker, notification)(signal, 261.5, *([1] if notification.endswith("warning") else []))
    assert len(messages) == 1
    assert messages[0]["chat_id"] == 1
    assert signal["signal_id"] in messages[0]["text"]
    assert "stop-loss moved" not in messages[0]["text"]


@pytest.mark.asyncio
async def test_persist_outcome_does_not_write_after_failed_evidence_read(monkeypatch):
    from contextlib import asynccontextmanager
    from engine.realtime_outcome_tracker import _persist_outcome
    write = AsyncMock()

    @asynccontextmanager
    async def scope(**_kwargs):
        yield SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("database_unavailable")))

    monkeypatch.setattr("db.session.get_session", scope)
    monkeypatch.setattr("db.pg_features.upsert_outcome", write)
    await _persist_outcome("missing-evidence", "tp1", 262.2601, 262.45)
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_entry_writer_rejects_expiry_under_lifecycle_lock(monkeypatch):
    from contextlib import asynccontextmanager
    from engine.signal_lifecycle import record_lifecycle_event
    rollback = AsyncMock()
    results = iter([SimpleNamespace(state=WATCHING_FOR_ENTRY), None])

    async def execute(_query):
        value = next(results)
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    @asynccontextmanager
    async def scope(**_kwargs):
        yield SimpleNamespace(execute=execute, rollback=rollback)

    monkeypatch.setattr("db.session.get_session", scope)
    monkeypatch.setenv("OUTCOME_LIFECYCLE_ENABLED", "1")
    signal = {"signal_id": "expired-entry", **vars(_jnj()), "expires_at": datetime.utcnow() - timedelta(seconds=1)}
    assert await record_lifecycle_event(signal, "entry_touched", 262.2) is False
    rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_tracker_rejected_entry_does_not_advance_or_book_tp(monkeypatch):
    from engine.realtime_outcome_tracker import OutcomePriceObservation, RealtimeOutcomeTracker
    record = AsyncMock(return_value=False)
    persist = AsyncMock()
    monkeypatch.setattr("engine.signal_lifecycle.update_lifecycle_observation", AsyncMock(return_value=WATCHING_FOR_ENTRY))
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", record)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_tp_progress", AsyncMock(return_value=0))
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", AsyncMock())
    monkeypatch.setenv("OUTCOME_LIFECYCLE_ENABLED", "1")
    monkeypatch.setenv("SIGNAL_ENTRY_GATING_ENABLED", "1")
    signal = {"signal_id": "entry-race", "asset": "JNJ", **vars(_jnj()),
              "lifecycle_state": WATCHING_FOR_ENTRY, "expires_at": datetime.utcnow() + timedelta(hours=1)}
    await RealtimeOutcomeTracker()._check_signal(signal, OutcomePriceObservation("JNJ", 260.8, "test", "now", True))
    assert signal["lifecycle_state"] == WATCHING_FOR_ENTRY
    assert record.await_count == 1
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_tracker_time_limit_closes_active_without_expiry_event(monkeypatch):
    from engine.realtime_outcome_tracker import OutcomePriceObservation, RealtimeOutcomeTracker
    record = AsyncMock(return_value=True)
    persist = AsyncMock()
    monkeypatch.setattr("engine.signal_lifecycle.update_lifecycle_observation", AsyncMock(return_value=ACTIVE_TRADE))
    monkeypatch.setattr("engine.signal_lifecycle.record_lifecycle_event", record)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_tp_progress", AsyncMock(return_value=0))
    monkeypatch.setattr("engine.realtime_outcome_tracker._persist_outcome", persist)
    monkeypatch.setattr("engine.realtime_outcome_tracker._publish_outcome_snapshot", AsyncMock())
    monkeypatch.setattr("core.redis_state.state.cache_set", AsyncMock())
    monkeypatch.setenv("OUTCOME_TIME_STOP_HOURS", "24")
    signal = {"signal_id": "time-limit", "asset": "US30", "direction": "long", "entry": 100,
              "stop_loss": 95, "take_profit": [110, 120, 130], "lifecycle_state": ACTIVE_TRADE,
              "created_at": datetime.utcnow() - timedelta(hours=25), "timeframe": "1h"}
    await RealtimeOutcomeTracker()._check_signal(signal, OutcomePriceObservation("US30", 101, "test", "now", True))
    assert record.await_args.args[1] == "time_stop"
    assert signal["lifecycle_state"] == CLOSED_TIME_STOP
    persist.assert_awaited_once_with("time-limit", "time_stop", 100.0, 101.0)
