from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_expire_job_excludes_unresolved_tracked_states() -> None:
    bot_path = ROOT / "signalrank_telegram" / "bot.py"
    source = bot_path.read_text(encoding="utf-8")
    assert "Outcome.status.in_([\"tp1\", \"tp2\"])" in source
    assert "~unresolved_tracked" in source


def test_outcome_notification_idempotency_wired_in_pg_features() -> None:
    pg_path = ROOT / "db" / "pg_features.py"
    source = pg_path.read_text(encoding="utf-8")
    assert "queue_outcome_notifications_for_outcome" in source
    assert "idempotency_key = f\"outcome:{signal_id}:{int(telegram_user_id)}:{status_l}\"" in source
    assert "OutcomeNotification.idempotency_key == idempotency_key[:128]" in source


def test_realtime_tracker_queues_and_delivers_from_db_state() -> None:
    tracker_path = ROOT / "engine" / "realtime_outcome_tracker.py"
    source = tracker_path.read_text(encoding="utf-8")
    assert "queue_outcome_notifications_for_outcome" in source
    assert "OutcomeNotification.delivery_state.in_([\"pending\", \"failed\"])" in source
    assert "mark_outcome_notification_delivered" in source


def test_signal_delivery_contract_requires_successful_delivery_rows() -> None:
    pg_path = ROOT / "db" / "pg_features.py"
    bot_path = ROOT / "signalrank_telegram" / "bot.py"
    commands_path = ROOT / "signalrank_telegram" / "commands.py"

    pg_source = pg_path.read_text(encoding="utf-8")
    bot_source = bot_path.read_text(encoding="utf-8")
    commands_source = commands_path.read_text(encoding="utf-8")

    assert "SignalDelivery.sent_ok.is_(True)" in pg_source
    assert "SignalDelivery.sent_ok.is_(True)" in bot_source
    assert "SignalDelivery.sent_ok.is_(True)" in commands_source
