from __future__ import annotations

import importlib
from pathlib import Path


def test_outcome_tracker_defaults_to_critical(monkeypatch):
    monkeypatch.delenv("OUTCOME_TRACKER_DB_PRIORITY", raising=False)
    monkeypatch.delenv("OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS", raising=False)
    module = importlib.import_module("engine.realtime_outcome_tracker")
    assert module._outcome_db_priority() == "critical"
    assert module._outcome_db_timeout() == 12.0


def test_outcome_tracker_rejects_background_priority(monkeypatch):
    monkeypatch.setenv("OUTCOME_TRACKER_DB_PRIORITY", "background")
    module = importlib.import_module("engine.realtime_outcome_tracker")
    assert module._outcome_db_priority() == "critical"


def test_webhook_handler_readiness_requires_full_contract():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    assert 'BOT_WEBHOOK_READY_MIN_HANDLERS", "60"' in source
    assert "total_handlers += len(handler_list or [])" in source
    assert "handlers_ready = handlers_flag and handlers_detected" in source
    assert "handlers_ready = handlers_flag or handlers_detected" not in source


def test_bot_source_refuses_partial_webhook_startup():
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    assert "_webhook_application = None" in source
    assert "refusing partial startup" in source
    assert "adaptive owner commands unavailable; continuing with core callbacks" in source
    assert "immediate callback ack guard registered" in source


def test_outcome_source_uses_operational_lane_and_scan_evidence():
    source = Path("engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert 'OUTCOME_TRACKER_DB_PRIORITY", "critical"' in source
    assert 'label="outcome_tracker.fetch_active_signals"' in source
    assert "[outcome_tracker] active_scan fetched=%d" in source
    assert "[outcome_tracker] reconciliation_backfill fetched=%d" in source


def test_staging_profile_enables_outcome_notifications():
    profile = Path(
        "SignalRankAI_v1.2.6_Railway_Full_System_Live_Paystack_Staging.env.example"
    ).read_text(encoding="utf-8")
    required = {
        "APP_VERSION=1.2.6",
        "BOT_WEBHOOK_READY_MIN_HANDLERS=60",
        "OUTCOME_TRACKER_DB_PRIORITY=critical",
        "OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS=12",
        "LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED=1",
        "SEND_OUTCOME_NOTIFICATIONS_ENABLED=1",
    }
    assert required.issubset(set(profile.splitlines()))


def test_lifecycle_recipient_states_are_normalized():
    source = Path("engine/signal_lifecycle.py").read_text(encoding="utf-8")
    assert 'func.lower(SignalDelivery.delivery_state).in_(("confirmed", "delivered", "reconciled"))' in source
