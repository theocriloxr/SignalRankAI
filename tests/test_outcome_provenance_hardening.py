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
    source = open("engine/realtime_outcome_tracker.py", encoding="utf-8").read()
    assert "SignalDelivery.telegram_message_id.is_not(None)" in source
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" in source
    assert '"LIVE_DELIVERED"' in source
