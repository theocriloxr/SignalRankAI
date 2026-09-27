from __future__ import annotations

import json
from pathlib import Path

from services.broker_connections import _connection_limit
from services.mt5_client import (
    _account_provisioning_payload,
    _metaapi_provisioning_error,
)


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_metaapi_string_details_authentication_error_is_classified() -> None:
    result = _metaapi_provisioning_error(
        400,
        json.dumps(
            {
                "error": "ValidationError",
                "message": "We failed to authenticate to your broker using credentials provided.",
                "details": "E_AUTH",
            }
        ),
    )
    assert result["code"] == "authentication_failed"
    assert result["provider_code"] == "E_AUTH"
    assert result["can_use_secure_link"] is True


def test_metaapi_settings_detection_error_requests_profile_fallback() -> None:
    result = _metaapi_provisioning_error(
        400,
        json.dumps(
            {
                "error": "ValidationError",
                "message": "We were not able to retrieve server settings using credentials provided.",
                "details": "E_SERVER_TIMEZONE",
            }
        ),
    )
    assert result["code"] == "broker_settings_detection_failed"
    assert "provisioning profile" in result["error"].lower()


def test_metaapi_server_suggestions_are_bounded_and_exposed() -> None:
    result = _metaapi_provisioning_error(
        400,
        json.dumps(
            {
                "message": "Server not found",
                "details": {
                    "code": "E_SRV_NOT_FOUND",
                    "serversByBrokers": {
                        "Broker": ["Broker-Demo", "Broker-Trade"],
                    },
                },
            }
        ),
    )
    assert result["code"] == "server_not_found"
    assert result["suggested_servers"] == ["Broker-Demo", "Broker-Trade"]


def test_operator_provisioning_profile_replaces_platform_detection(monkeypatch) -> None:
    monkeypatch.setenv(
        "META_API_PROVISIONING_PROFILE_MAP_JSON",
        json.dumps({"mt5:assexmarketsglobal-trade": "profile-123"}),
    )
    payload = _account_provisioning_payload(
        user_id=10,
        platform="mt5",
        server="AssexmarketsGlobal-Trade",
        account_label="Demo",
        broker_name="Assexmarkets Global Limited",
        login="12345",
        password="secret",
        source="test",
    )
    assert payload["provisioningProfileId"] == "profile-123"
    assert "platform" not in payload
    assert payload["server"] == "AssexmarketsGlobal-Trade"


def test_paid_plans_are_multi_account_and_limits_are_overridable(monkeypatch) -> None:
    assert _connection_limit("PREMIUM") >= 2
    assert _connection_limit("VIP") > _connection_limit("PREMIUM")
    monkeypatch.setenv("BROKER_CONNECTION_LIMIT_PREMIUM", "7")
    assert _connection_limit("PREMIUM") == 7


def test_web_mt5_form_distinguishes_company_from_exact_server() -> None:
    html = source("web/platform_app/index.html")
    assert "Broker / company" in html
    assert "Exact MetaTrader server" in html
    assert "AssexmarketsGlobal-Trade" in html
    assert "brokerProvisioningResult" in html
    assert "broker-account-grid" in html


def test_web_uses_structured_mt5_recovery_and_account_cards() -> None:
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    assert "error.detail=detail" in app
    assert "suggested_servers" in app
    assert "server-suggestion" in app
    assert "broker-account-card" in app
    assert '"suggested_servers": list(result.get("suggested_servers") or [])' in api


def test_telegram_merge_review_is_treated_as_verified_not_reconnect() -> None:
    identity = source("services/platform/identity.py")
    app = source("web/platform_app/app.js")
    mobile = source("mobile/App.tsx")
    api = source("web/platform_api.py")
    assert 'telegram_status = "merge_review"' in identity
    assert "telegram_connected_or_pending" in identity
    assert "Telegram ownership is already verified" in api
    assert "Account history reconciliation is pending; you do not need to reconnect." in app
    assert "telegramStatus==='merge_review'" in mobile


def test_tablet_navigation_breakpoint_avoids_early_fixed_sidebar() -> None:
    css = source("web/platform_app/styles.css")
    assert "@media(min-width:1320px)" in css
    assert "@media(max-width:1319px) and (min-width:701px)" in css
    assert ".broker-account-grid" in css
