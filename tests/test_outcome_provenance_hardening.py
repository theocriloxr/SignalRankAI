from pathlib import Path
from types import SimpleNamespace

from engine.outcome_eligibility import (
    BACKTEST,
    INVALIDATED_UNDELIVERED,
    LEGACY_UNVERIFIED,
    LIVE_DELIVERED,
    PAPER,
    SHADOW,
    evaluate_outcome_eligibility,
)


def _delivery(**overrides):
    values = dict(
        id=42,
        sent_ok=True,
        telegram_chat_id=100,
        telegram_message_id=200,
        delivery_confirmed_at="2026-07-25T00:00:00Z",
        delivery_state="confirmed",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_live_delivery_requires_complete_proof():
    result = evaluate_outcome_eligibility(
        {"lifecycle_state": "WATCHING_FOR_ENTRY"},
        _delivery(),
    )
    assert result.eligible is True
    assert result.category == LIVE_DELIVERED


def test_missing_message_id_is_not_live():
    result = evaluate_outcome_eligibility({}, _delivery(telegram_message_id=None))
    assert result.eligible is False
    assert result.category == INVALIDATED_UNDELIVERED


def test_no_delivery_is_legacy_unverified():
    result = evaluate_outcome_eligibility({"lifecycle_state": "ACTIVE"}, None)
    assert result.eligible is False
    assert result.category == LEGACY_UNVERIFIED


def test_non_live_categories_never_enter_live_metrics():
    assert evaluate_outcome_eligibility({"is_shadow": True}, _delivery()).category == SHADOW
    assert evaluate_outcome_eligibility({"is_paper": True}, _delivery()).category == PAPER
    assert evaluate_outcome_eligibility({"is_backtest": True}, _delivery()).category == BACKTEST


def test_tracker_queries_proof_backed_deliveries_only():
    source = Path("engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "SignalDelivery.telegram_message_id.is_not(None)" in source
    assert "SignalDelivery.sent_ok.is_(True)" in source
    assert "func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES)" in source
    assert '"LIVE_DELIVERED"' in source



def test_tracker_accepts_gated_web_receipts_without_weakening_telegram_proof():
    source = Path("engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "def _verified_telegram_delivery_exists(" in source
    assert "SignalDelivery.sent_ok.is_(True)" in source
    assert "SignalDelivery.telegram_chat_id.is_not(None)" in source
    assert "SignalDelivery.telegram_message_id.is_not(None)" in source
    assert "func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES)" in source
    assert "def _web_signal_receipt_exists_clause()" in source
    assert "notification_events ne" in source
    assert "ne.channel_data->>'channel'='web'" in source
    assert "ne.channel_data->>'signal_id'=signals.signal_id" in source
    assert "or_(" in source[source.index("async def _fetch_active_signals"):source.index("async def _fetch_delivered_untracked_signals")]


def test_web_lifecycle_notifications_are_idempotent_and_tier_scoped():
    source = Path("engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def _notify_web_outcome("):
        source.index("async def _broadcast_state_change")
    ]
    assert "uuid5(" in section
    assert "signalrank:web-outcome:" in section
    assert "ON CONFLICT(notification_id) DO NOTHING" in section
    assert "get_entitlements(tier).max_tp_levels" in section
    assert "COALESCE(np.web_enabled, TRUE) IS TRUE" in section
    assert "COALESCE(u.is_blocked, FALSE) IS FALSE" in section
    assert "COALESCE(u.is_suspended, FALSE) IS FALSE" in section
    broadcast = source[
        source.index("async def _broadcast_state_change"):
        source.index("def _check_interval")
    ]
    assert "await _notify_outcome(signal_dict, status, price)" in broadcast
    assert "await _notify_web_outcome(signal_dict, status, price)" in broadcast
