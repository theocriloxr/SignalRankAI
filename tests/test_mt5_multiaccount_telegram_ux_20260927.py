from __future__ import annotations

import json
from pathlib import Path
from scripts.assert_portal_assets import validate_shell_assets

from services.broker_connections import _connection_limit
from services.mt5_client import (
    _account_provisioning_payload,
    _client_base,
    _metaapi_client_domain,
    _metaapi_provisioning_domain,
    _metaapi_provisioning_error,
    _metaapi_region,
    _metaapi_token_candidates,
    _provisioning_base,
)


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_metaapi_client_url_uses_documented_regional_host(monkeypatch) -> None:
    monkeypatch.delenv("META_API_DOMAIN", raising=False)
    monkeypatch.delenv("META_API_REGION", raising=False)
    assert _metaapi_client_domain() == "agiliumtrade.ai"
    assert _metaapi_provisioning_domain() == "agiliumtrade.agiliumtrade.ai"
    assert _metaapi_region() == "new-york"
    assert _client_base() == "https://mt-client-api-v1.new-york.agiliumtrade.ai/users/current/accounts"
    assert _client_base("account-123") == "https://mt-client-api-v1.new-york.agiliumtrade.ai/users/current/accounts/account-123"
    assert _provisioning_base() == "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts"


def test_metaapi_legacy_host_configuration_is_normalized(monkeypatch) -> None:
    monkeypatch.setenv("META_API_DOMAIN", "agiliumtrade.agiliumtrade.ai")
    monkeypatch.setenv("META_API_REGION", "mt-client-api-v1")
    assert _metaapi_client_domain() == "agiliumtrade.ai"
    assert _metaapi_provisioning_domain() == "agiliumtrade.agiliumtrade.ai"
    assert _metaapi_region() == "new-york"
    assert "agiliumtrade.agiliumtrade.ai" not in _client_base()
    assert _client_base().startswith("https://mt-client-api-v1.new-york.agiliumtrade.ai/")


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


def test_manual_execution_can_target_an_explicit_connected_account() -> None:
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    assert "executionConnectionSelect" in app
    assert "connection_id:connection.connection_id" in app
    assert "connection_id: str | None" in api


def test_compact_workspace_switcher_replaces_tablet_nav_clutter() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    css = source("web/platform_app/styles.css")
    sw = source("web/platform_app/service-worker.js")
    assert 'id="compactNav"' in html
    assert 'id="viewSwitcher"' in html
    from html import unescape

    assert "Account & brokers" in unescape(html)
    assert "$('#viewSwitcher')?.addEventListener('change'" in app
    assert "body.session-active #sessionNav{display:none!important}" in css
    assert "body.session-active .compact-nav{display:block!important" in css
    assert validate_shell_assets(ROOT) >= 38


def test_metaapi_failure_contract_exposes_operator_recovery_fields() -> None:
    api = source("web/platform_api.py")
    mt5 = source("services/mt5_client.py")
    assert '"recommended_resource_slots"' in mt5
    assert "META_API_PROVISIONING_PROFILE_MAP_JSON" in mt5
    assert "[metatrader] provisioning_failed" in mt5
    assert "server_not_found" in api
    assert "broker_settings_detection_failed" in api
    assert "provider_rate_limited" in api


def test_known_server_preflight_is_credential_free_and_wired_to_ui() -> None:
    mt5 = source("services/mt5_client.py")
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    assert "async def search_known_metatrader_servers(" in mt5
    assert "/known-mt-servers/{version}/search" in mt5
    assert 'params={"query": query_n}' in mt5
    assert "login" not in mt5[
        mt5.index("async def search_known_metatrader_servers("):
        mt5.index("def _slippage_tolerance")
    ]
    assert '@router.get("/broker/metatrader/servers")' in api
    assert 'id="brokerServerLookupButton"' in html
    assert 'id="brokerServerLookupResult"' in html
    assert "known-server-choice" in app
    assert "No trading password is sent when searching." in html


def test_metaapi_http_401_is_operator_token_failure_not_broker_auth() -> None:
    result = _metaapi_provisioning_error(
        401,
        json.dumps(
            {
                "error": "UnauthorizedError",
                "message": "Authorization failed",
            }
        ),
    )
    assert result["code"] == "provider_authorization_failed"
    assert result["provider_code"] == "UnauthorizedError"
    assert result["can_use_secure_link"] is False
    assert "MetaApi API token" in result["error"]
    assert "MT4/MT5 credentials were not the cause" in result["error"]


def test_metaapi_http_403_is_operator_permission_failure() -> None:
    result = _metaapi_provisioning_error(
        403,
        json.dumps(
            {
                "error": "ForbiddenError",
                "message": "Method or resource access permissions are missing",
            }
        ),
    )
    assert result["code"] == "provider_permissions_missing"
    assert result["can_use_secure_link"] is False
    assert "permissions" in result["error"].lower()


def test_broker_e_auth_remains_distinct_from_metaapi_token_auth() -> None:
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


def test_runtime_actively_probes_metaapi_token_instead_of_presence_only() -> None:
    mt5 = source("services/mt5_client.py")
    runtime = source("railway_main.py")
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    sw = source("web/platform_app/service-worker.js")
    assert "async def probe_metaapi_authorization(*, force: bool = False)" in mt5
    assert "[metaapi_startup_probe] status=PASS" in runtime
    assert "[metaapi_startup_probe] status=FAIL" in runtime
    assert "provider_permissions_missing" in api
    assert "integration problem, not an error in your broker login/server" in app
    assert validate_shell_assets(ROOT) >= 38


def test_broker_workspace_fails_closed_when_metaapi_auth_is_unhealthy() -> None:
    mt5 = source("services/mt5_client.py")
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    css = source("web/platform_app/styles.css")
    sw = source("web/platform_app/service-worker.js")
    assert "_METAAPI_AUTH_CACHE" in mt5
    assert "META_API_AUTH_PROBE_CACHE_SECONDS" in mt5
    assert '"provider_health": {' in api
    assert '"metaapi": metaapi_health' in api
    assert 'id="brokerProviderHealth"' in html
    assert "MetaTrader connection temporarily unavailable" in app
    assert "Your MT4/MT5 login, password and server are not the cause" in app
    assert "control.disabled=!metaapiReady" in app
    assert "provider-health-error" in css
    assert validate_shell_assets(ROOT) >= 38


def test_metaapi_token_alias_candidates_are_ordered_and_deduplicated(monkeypatch) -> None:
    monkeypatch.setenv("META_API_TOKEN", "canonical-stale")
    monkeypatch.setenv("METAAPI_TOKEN", "legacy-valid")
    assert _metaapi_token_candidates() == [
        ("META_API_TOKEN", "canonical-stale"),
        ("METAAPI_TOKEN", "legacy-valid"),
    ]
    monkeypatch.setenv("METAAPI_TOKEN", "canonical-stale")
    assert _metaapi_token_candidates() == [
        ("META_API_TOKEN", "canonical-stale"),
    ]


def test_metaapi_alias_selection_is_wired_across_runtime_gates() -> None:
    mt5 = source("services/mt5_client.py")
    runtime = source("railway_main.py")
    api = source("web/platform_api.py")
    broker = source("services/broker_connections.py")
    worker = source("worker/worker.py")
    activation = source("core/financial_activation.py")
    data = source("data/get_live_price.py")

    assert 'for env_name in ("META_API_TOKEN", "METAAPI_TOKEN")' in mt5
    assert "for env_name, token in candidates:" in mt5
    assert "_METAAPI_ACTIVE_TOKEN_ENV = env_name" in mt5
    # Runtime readiness may report only whether MetaApi is configured. It must
    # not reveal which secret alias supplied the active credential.
    assert "token_source=%s" not in runtime
    assert "active_token_env" not in runtime
    assert 'os.getenv("METAAPI_TOKEN")' in runtime
    assert 'os.getenv("METAAPI_TOKEN")' in api
    assert 'os.getenv("METAAPI_TOKEN")' in broker
    assert 'os.getenv("METAAPI_TOKEN")' in worker
    assert '_raw(environ, "METAAPI_TOKEN")' in activation
    assert 'os.getenv("METAAPI_TOKEN")' in data
