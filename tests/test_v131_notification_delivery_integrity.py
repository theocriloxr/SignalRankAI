from __future__ import annotations

import inspect
from pathlib import Path

from engine.signal_lifecycle import _should_queue_event_notification, dispatch_event_notifications
from engine.tier_notifications import TierNotificationManager
from utils.trade_levels import parse_price_levels

ROOT = Path(__file__).resolve().parents[1]


def test_json_encoded_targets_are_not_iterated_character_by_character():
    raw = "[73.74485714, 73.81228571, 73.91342857]"
    assert parse_price_levels(raw) == [73.74485714, 73.81228571, 73.91342857]

    message = TierNotificationManager().format_tp_hit_notification(
        {
            "signal_id": "f0c67e7d-0ee",
            "asset": "SOLUSDT",
            "direction": "long",
            "timeframe": "5m",
            "entry": 73.61,
            "stop_loss": 73.50042857,
            "take_profit": raw,
        },
        "vip",
        3,
        1.39,
        74.5,
    )
    assert "TP1: 73.7449" in message
    assert "TP2: 73.8123" in message
    assert "TP3: 73.9134" in message
    assert "TP4:" not in message
    assert "Remaining:" not in message
    assert "Signal P/L: +1.39%" in message


def test_lifecycle_updates_never_replace_the_original_signal_card(monkeypatch):
    source = inspect.getsource(dispatch_event_notifications)
    assert "edit_message_text" not in source
    assert "reply_to_message_id" in source
    assert '"disable_notification": False' in source
    monkeypatch.delenv("LIFECYCLE_TP_SL_NOTIFICATIONS_ENABLED", raising=False)
    assert _should_queue_event_notification("entry_touched") is True
    assert _should_queue_event_notification("tp3_hit") is False
    assert _should_queue_event_notification("sl_hit") is False


def test_primary_signal_and_outcome_sends_are_explicitly_non_silent():
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "disable_notification=False" in source
    assert "Live refresh is temporarily busy" in source
    assert "Outcome check is busy right now" not in source


def test_production_profiles_enable_fast_recovery_without_edit_delivery():
    for filename in (
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example",
    ):
        profile = (ROOT / filename).read_text(encoding="utf-8")
        for marker in (
            "DELIVERY_SIGNAL_UPDATE_ENABLED=0",
            "LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED=1",
            "LIFECYCLE_TP_SL_NOTIFICATIONS_ENABLED=0",
            "SEND_OUTCOME_NOTIFICATIONS_ENABLED=1",
            "TELEGRAM_SEND_MAX_ATTEMPTS=3",
            "RESEND_UNSENT_INTERVAL_SECONDS=30",
        ):
            assert marker in profile


def test_production_readiness_rejects_silent_or_duplicate_notification_modes():
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "duplicate_tp_sl_notification_dispatchers_enabled" in source
    assert "signal_delivery_edit_mode_enabled" in source
    assert "telegram_send_retries_too_low" in source
    assert "unsent_signal_recovery_interval_too_high" in source
