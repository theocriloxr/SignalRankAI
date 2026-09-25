from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
APP_HTML = (ROOT / "web/platform_app/index.html").read_text(encoding="utf-8")
API = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")


def test_multi_element_dom_operations_use_query_selector_all_helper():
    bad = re.findall(r"(?<!\$)\$\('#[^']+'\)\.(?:map|forEach)\(", APP_JS)
    assert bad == []


def test_trading_profile_market_checkboxes_use_multi_selector():
    assert "$$('#tradingProfileForm input[name=\"asset_class\"]').forEach(" in APP_JS
    assert "document.querySelectorAll(\'#tradingProfileForm input[name=\"asset_class\"]:checked\')" in APP_JS


def test_signal_filters_cover_every_supported_market_class():
    for market in ("crypto", "fx", "stock", "index", "commodity"):
        assert f'<option value="{market}">' in APP_HTML
    assert "signalClassFilter" in APP_JS
    assert "signalTimeframeFilter" in APP_JS
    assert "signalStrategyFilter" in APP_JS


def test_web_user_toolkit_is_wired_to_real_api_routes():
    routes = (
        "/live-price",
        "/recap",
        "/ai/analyze",
        "/watchlists",
        "/alerts",
        "/notifications",
        "/signals/",
        "/paper/settings",
        "/paper/close-all",
        "/paper/reset",
        "/trading-profile",
    )
    for route in routes:
        assert route in APP_JS
        assert route in API


def test_web_boot_is_resilient_to_optional_paid_surfaces():
    assert "Promise.allSettled(initial)" in APP_JS
    assert "hasFeature('paper_trading')" in APP_JS
    assert "applyEntitlements()" in APP_JS


def test_profile_ui_exposes_locale_quiet_hours_and_cross_channel_sync():
    for needle in (
        'name="locale"',
        'name="quiet_hours_start"',
        'name="quiet_hours_end"',
        'id="tradingProfileForm"',
        "Synced with your linked Telegram account",
    ):
        assert needle in APP_HTML or needle in APP_JS


def test_service_worker_shell_version_was_rotated_for_current_frontend():
    sw = (ROOT / "web/platform_app/service-worker.js").read_text(encoding="utf-8")
    assert re.search(r"signalrank-shell-v([3-9]|[1-9][0-9]+)", sw)



def test_web_broker_and_quality_parity_is_wired_to_real_routes():
    for route in (
        "/quality",
        "/shadow-report",
        "/broker",
        "/broker/metatrader",
        "/execution-settings",
        "/execution-terms/accept",
    ):
        assert route in APP_JS
        assert route in API
    for element_id in (
        "brokerPanel",
        "brokerLinkForm",
        "executionSettingsForm",
        "qualitySummary",
        "shadowSummary",
    ):
        assert f'id="{element_id}"' in APP_HTML


def test_broker_password_is_never_rendered_back_to_the_browser():
    assert "password_encrypted" not in APP_JS
    broker_section = API[API.index('@router.get("/broker")'):API.index('@router.delete("/devices/{session_id}")')]
    assert '"password_encrypted"' not in broker_section
    assert "mt5_password" in broker_section
    assert "get_platform_mt5_link_status" in broker_section


def test_live_execution_controls_preserve_non_bypassable_entitlement_gates():
    section = API[API.index('@router.put("/execution-settings")'):API.index('@router.delete("/devices/{session_id}")')]
    assert '_assert_command(user, "execution")' in section
    assert '_assert_feature(user, "execution_preflight")' in section
    assert "get_platform_metatrader_connection" in section
    assert "accepted_terms" not in section or '@router.post("/execution-terms/accept")' in API


def test_quality_and_shadow_reports_are_kept_separate_from_live_performance():
    assert '@router.get("/quality")' in API
    assert '@router.get("/shadow-report")' in API
    shadow = API[API.index('@router.get("/shadow-report")'):API.index('@router.get("/strategy-leaderboard")')]
    assert "counterfactual" in shadow.lower()
    assert '"claim_certified"] = False' in shadow



def test_signal_feedback_is_delivery_scoped_and_canonical():
    assert '@router.post("/signals/{signal_id}/feedback"' in API
    section = API[
        API.index('@router.post("/signals/{signal_id}/feedback"'):
        API.index('@router.get("/live-price")')
    ]
    assert '_assert_command(user, "feedback")' in section
    assert "signal_deliveries" in section
    assert "sent_ok=TRUE" in section
    assert "record_user_event" in section
    assert '"source": "web"' in section
    assert "/feedback" in APP_JS
    assert 'id="signalFeedbackForm"' in APP_JS
    assert "wrong_outcome" in APP_JS



def test_web_signal_fanout_is_a_distinct_gated_delivery_channel():
    fanout = (ROOT / "services/platform/signal_delivery.py").read_text(encoding="utf-8")
    worker = (ROOT / "worker/worker.py").read_text(encoding="utf-8")
    assert "notification_events" in fanout
    assert '"channel": "web"' in fanout
    assert "require_delivery_freshness=True" in fanout
    assert "final_send=True" in fanout
    assert "signal_matches_preferences" in fanout
    assert "minimum_signal_score" in fanout
    assert "_daily_distinct_count" in fanout
    assert "_recent_assets" in fanout
    assert "INSERT INTO signal_deliveries" not in fanout
    assert 'if _env_bool("WEB_SIGNAL_FANOUT_ENABLED", True):' in worker
    assert '_register_task(' in worker
    assert '"web_signal_fanout"' in worker
    assert "self._web_signal_fanout_loop()" in worker


def test_signal_feed_accepts_web_receipts_without_weakening_telegram_proof():
    section = API[API.index('@router.get("/signals")'):API.index('@router.get("/live-price")')]
    assert "notification_events" in section
    assert "'telegram'::text AS delivery_channel" in section
    assert "'web'::text AS delivery_channel" in section
    assert '"web_delivery_proven": web_proven' in section
    assert '"delivery_proven": telegram_proven' in section
    assert "telegram_message_id" in section
    assert "Signal receipt confirmed" in APP_JS
    assert "Telegram proof:" in APP_JS
    assert "Web receipt:" in APP_JS


def test_feedback_accepts_either_authorized_signal_receipt():
    section = API[
        API.index('@router.post("/signals/{signal_id}/feedback"'):
        API.index('@router.get("/live-price")')
    ]
    assert "signal_deliveries" in section
    assert "notification_events" in section
    assert "record_user_event" in section



def test_web_manual_execution_reuses_canonical_mt5_gate():
    assert '@router.post("/signals/{signal_id}/execute")' in API
    section = API[
        API.index('@router.post("/signals/{signal_id}/execute"'):
        API.index('@router.post("/signals/{signal_id}/feedback"')
    ]
    assert '_assert_feature(user, "broker_connection")' in section
    assert "payload.confirm is not True" in section
    assert "signal_deliveries" in section
    assert "notification_events" in section
    assert "route_platform_signal_to_metatrader" in section
    assert 'execution_mode="manual_confirmed"' in section
    assert "execute_trade(" not in section
    assert "/execute" in APP_JS
    assert "Confirm and submit to MT5" in APP_JS
    assert "/broker/connections" in APP_JS
    assert "/broker/metatrader" in APP_JS
    assert "/broker/metatrader/secure-link" in APP_JS
    assert "The server will block the trade" in APP_JS


def test_web_execution_settings_resolve_saved_provider_before_live_validation():
    section = API[
        API.index('@router.put("/execution-settings")'):
        API.index('@router.delete("/devices/{session_id}")')
    ]
    assert "effective_provider" in section
    assert "current.execution_provider" in section
    assert 'effective_provider != "bybit"' in section



def test_web_notification_center_receives_signal_lifecycle_events():
    tracker = (ROOT / "engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "'signal_outcome'" in tracker
    assert '"surface": "signal_lifecycle"' in tracker
    assert '"outcome_status": status_l' in tracker
    assert '@router.get("/notifications")' in API



def test_signal_api_enforces_telegram_equivalent_tier_visibility():
    assert "def _present_signal_for_tier(" in API
    section = API[
        API.index("def _present_signal_for_tier("):
        API.index("def _assert_feature(")
    ]
    assert 'payload["entry"] = None' in section
    assert 'payload["stop_loss"] = None' in section
    assert 'payload["rr_estimate"] = None' in section
    assert 'payload["score"] = None' in section
    assert 'payload["ml_probability"] = None' in section
    assert 'payload["ml_probability_calibrated"] = None' in section
    assert 'payload["take_profit"] = targets[: int(policy.max_tp_levels)]' in section
    assert 'payload["exact_levels_locked"]' in section
    assert "performance_analytics" in section
    assert "detailed_provenance" in section
    assert "lifecycle_updates" in section
    feed = API[API.index('@router.get("/signals")'):API.index('@router.get("/signals/{signal_id}")')]
    detail = API[API.index('@router.get("/signals/{signal_id}")'):API.index('@router.post("/signals/{signal_id}/execute")')]
    assert "_present_signal_for_tier" in feed
    assert "_present_signal_for_tier" in detail
    assert "_present_signal_events_for_tier" in detail
    assert "Premium only" in APP_JS


def test_web_signal_fanout_honors_tier_asset_and_delay_policy():
    source = (ROOT / "services/platform/signal_delivery.py").read_text(encoding="utf-8")
    assert '"delivery_delay_minutes": int(policy.delivery_delay_minutes)' in source
    assert '"allowed_asset_classes": tuple(policy.allowed_asset_classes)' in source
    assert 'signal_class not in set(user["allowed_asset_classes"])' in source
    assert 'signal_age_minutes < float(user["delivery_delay_minutes"])' in source
    assert 'counters["blocked_entitlement"]' in source
    assert 'counters["blocked_delay"]' in source



def test_web_signal_fanout_waits_for_db_capacity_instead_of_dropping():
    fanout = (ROOT / "services/platform/signal_delivery.py").read_text(encoding="utf-8")
    snapshot = fanout[
        fanout.index("async def _snapshot_candidates"):
        fanout.index("async def deliver_recent_web_signals")
    ]
    assert 'label="platform.web_signal_fanout.snapshot"' in snapshot
    assert "drop_if_busy=False" in snapshot
    assert "WEB_SIGNAL_FANOUT_DB_WAIT_SECONDS" in snapshot
    assert "drop_if_busy=True" not in snapshot
