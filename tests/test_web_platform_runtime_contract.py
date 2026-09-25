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
        "/broker/mt5",
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
    assert "get_platform_mt5_link_status" in section
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
