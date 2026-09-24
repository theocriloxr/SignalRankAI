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
    assert "$$('#tradingProfileForm input[name=\"asset_class\"]:checked').map(" in APP_JS


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
    assert "signalrank-shell-v3" in sw
