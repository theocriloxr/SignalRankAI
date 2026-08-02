from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
CALLBACKS = (ROOT / "signalrank_telegram" / "callback_handlers.py").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "engine" / "signal_lifecycle.py").read_text(encoding="utf-8")
READINESS = (ROOT / "railway_main.py").read_text(encoding="utf-8")


def test_v132_release_identity_is_exact():
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.6"
    assert RELEASE_FINGERPRINT == "v1.3.6-railway-performance-decomposition-20260802"


def test_signal_and_monitor_keyboards_have_durable_navigation():
    assert 'Monitor", callback_data=_signal_callback_data("monitor_signal_"' in BOT
    assert 'Open Signal", callback_data=_signal_callback_data("open_signal_"' in BOT
    assert 'Refresh", callback_data=_signal_callback_data("monitor_signal_"' in BOT
    assert '_signal_callback_data("open_signal_"' in BOT
    assert '_signal_callback_data("monitor_signal_"' in BOT


def test_open_signal_renders_fresh_authorized_card_instead_of_copying_stale_message():
    concrete = BOT[BOT.index("async def _open_signal_callback"):BOT.index("application.add_handler(_CQH(_open_signal_callback")]
    assert "_send_signal_card_for_user" in concrete
    assert "copy_message" not in concrete
    assert "ActiveSignalMessage" not in concrete
    assert '"disable_notification": False' in BOT[BOT.index("async def _send_signal_card_for_user"):BOT.index("async def _load_signal_engagement_counts")]

    fallback = CALLBACKS[CALLBACKS.index("async def _handle_open_signal"):CALLBACKS.index("async def _handle_locked")]
    assert "_send_signal_card_for_user" in fallback
    assert "pass" not in fallback


def test_monitor_refresh_never_overwrites_signal_card_and_recovers_failed_edits():
    concrete = BOT[BOT.index("async def _signal_monitor_callback"):BOT.index("application.add_handler(_CQH(_signal_monitor_callback")]
    assert 'runtime_key = f"monitor:' in concrete
    assert "edit_message_text" in concrete
    assert "edit failed; recreating" in concrete
    assert "message_id = None" in concrete
    assert "send_message" in concrete
    assert "%H:%M:%S UTC" in BOT

    fallback = CALLBACKS[CALLBACKS.index("async def _handle_monitor_signal"):CALLBACKS.index("async def _handle_check_outcome")]
    assert "edit_message_text" not in fallback
    assert "_build_monitor_snapshot" in fallback
    assert "_build_monitor_keyboard" in fallback


def test_monitor_does_not_misclassify_db_timeout_as_missing_delivery():
    payload_loader = BOT[BOT.index("async def _load_signal_payload"):BOT.index("async def _render_signal_card_for_user")]
    concrete = BOT[BOT.index("async def _signal_monitor_callback"):BOT.index("application.add_handler(_CQH(_signal_monitor_callback")]

    assert "except TimeoutError as exc:" in payload_loader
    assert "raise" in payload_loader[payload_loader.index("except TimeoutError as exc:"):]
    assert "Monitor refresh failed temporarily" in concrete


def test_monitor_reuses_authorized_payload_instead_of_resolving_it_twice():
    concrete = BOT[BOT.index("async def _signal_monitor_callback"):BOT.index("application.add_handler(_CQH(_signal_monitor_callback")]
    snapshot = BOT[BOT.index("async def _build_monitor_snapshot"):BOT.index("def _parse_tp_levels_for_outcome")]

    assert "signal_payload=resolved_payload" in concrete
    assert "signal_payload: dict | None = None" in snapshot
    assert "payload = signal_payload" in snapshot


def test_monitor_displays_real_best_price_separately_from_tp_progress():
    assert "max_price_seen" in BOT
    assert "min_price_seen" in BOT
    assert "Highest'} Price Seen" in BOT
    assert "Highest TP Reached" in BOT
    monitor_block = BOT[BOT.index("async def _build_monitor_snapshot"):BOT.index("def _parse_tp_levels_for_outcome")]
    assert "update_lifecycle_observation" not in monitor_block
    assert "outcome worker is the sole" in monitor_block.lower()
    assert "\u2022 Highest Target:" not in monitor_block


def test_proactive_lifecycle_and_outcome_messages_are_non_silent_and_actionable():
    assert '"disable_notification": False' in LIFECYCLE
    assert "_lifecycle_notification_keyboard" in LIFECYCLE
    assert 'callback_data=f"open_signal_{ref}"' in LIFECYCLE
    assert 'callback_data=f"monitor_signal_{ref}"' in LIFECYCLE

    outcome_block = BOT[BOT.index("def _send_outcome_notifications_owned"):BOT.index("def refresh_monitor_snapshots_job")]
    assert "reply_markup=_build_monitor_keyboard(str(ref))" in outcome_block
    assert "_send_message_with_retry_sync" in outcome_block


def test_delivery_recovery_runs_frequently_and_is_not_suppressed_by_fanout():
    assert '_env_bool("RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE", False)' in BOT
    assert 'RESEND_UNSENT_INTERVAL_SECONDS", "60"' in BOT
    assert 'RESEND_UNSENT_STARTUP_DELAY_SECONDS' in BOT
    assert 'OUTCOME_NOTIFICATION_INTERVAL_SECONDS", "90"' in BOT
    assert 'MONITOR_REFRESH_INTERVAL_SECONDS", "120"' in BOT
    assert 'RESEND_UNSENT_INTERVAL_SECONDS", os.getenv("RESEND_INTERVAL_SECONDS", "60")' in BOT
    assert 'RESEND_JOB_BUDGET_SECONDS", "20"' in BOT
    assert 'OUTCOME_NOTIFICATION_JOB_BUDGET_SECONDS", "20"' in BOT


def test_all_production_profiles_enable_global_automatic_delivery_contract():
    for filename in (
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example",
    ):
        profile = (ROOT / filename).read_text(encoding="utf-8")
        for marker in (
            "APP_ENV=production",
            "PUBLIC_TESTING_MODE=0",
            "FULL_SYSTEM_STAGING_TEST_MODE=0",
            "DELIVERY_AUDIENCE_ALLOWLIST=",
            "RESEND_AUDIENCE_ALLOWLIST_ONLY=0",
            "ENGINE_DELIVERY_ASYNC_FANOUT=1",
            "RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE=0",
            "RESEND_UNSENT_INTERVAL_SECONDS=30",
            "OUTCOME_NOTIFICATION_INTERVAL_SECONDS=30",
            "MONITOR_REFRESH_INTERVAL_SECONDS=60",
            "SEND_OUTCOME_NOTIFICATIONS_ENABLED=1",
            "LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED=1",
            "TELEGRAM_SEND_MAX_ATTEMPTS=3",
            "TELEGRAM_RICH_MESSAGES_ENABLED=0",
        ):
            assert marker in profile, f"{filename}: missing {marker}"


def test_production_readiness_rejects_configuration_that_breaks_delivery_or_buttons():
    for marker in (
        "unsent_signal_recovery_interval_too_high",
        "outcome_notification_interval_too_high",
        "monitor_refresh_interval_too_high",
        "resend_recovery_can_be_suppressed_by_fanout",
        "uncertified_rich_signal_delivery_enabled",
    ):
        assert marker in READINESS
