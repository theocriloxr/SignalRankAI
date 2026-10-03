from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_browser_session_restores_before_auth_shell_is_shown() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    assert 'id="bootstrapShell"' in html
    assert 'id="authShell" class="auth-shell" hidden' in html
    assert "refreshBrowserSession" in app
    assert "response.status===401" in app
    assert "return request(path,options,false)" in app
    assert "showBootstrapError" in app
    assert "if(Number(err?.status)===401)setLoggedIn(false);else showBootstrapError" in app
    assert 'id="bootstrapRetry"' in html


def test_tier_navigation_is_visibility_gated_and_server_policy_remains_authoritative() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    policy = source("core/tier_policy.py")
    assert 'data-feature="paper_trading"' in html
    assert 'data-feature="portfolio_analytics"' in html
    assert 'data-feature="performance_analytics"' in html
    assert "el.hidden=!allowed" in app
    assert '"broker_connection": Tier.PREMIUM' in policy
    assert '"rest_api": Tier.PROFESSIONAL' in policy


def test_secure_metaapi_handoff_is_persisted_and_reconciled_on_return() -> None:
    app = source("web/platform_app/app.js")
    mt5 = source("services/mt5_client.py")
    assert "SECURE_LINK_PENDING_KEY" in app
    assert "localStorage.setItem(SECURE_LINK_PENDING_KEY" in app
    assert "reconcilePendingSecureLink" in app
    assert "visibilitychange" in app
    assert "/verify" in app
    assert 'status="awaiting_credentials"' in mt5
    assert 'external_account_id=account_id' in mt5


def test_paystack_return_has_spa_route_and_provider_verified_confirmation() -> None:
    web = source("web/app.py")
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    assert '@app.get("/billing/complete"' in web
    assert '@router.post("/billing/confirm")' in api
    assert "/transaction/verify/" in api
    assert 'paid_user_id != int(user["id"])' in api
    assert 'process_event({"event": "charge.success", "data": transaction})' in api
    assert "location.pathname==='/billing/complete'" in app
    assert "confirmPendingBillingReturn" in app
    assert "state.pendingBillingReference" in app


def test_transactional_email_defaults_to_crilox_hello_identity() -> None:
    delivery = source("services/platform/email_delivery.py")
    env = source(".env.example")
    assert "SignalRankAI <hello@criloxsolutions.com>" in delivery
    assert 'EMAIL_REPLY_TO' in delivery
    assert "EMAIL_FROM=SignalRankAI <hello@criloxsolutions.com>" in env
    assert "EMAIL_REPLY_TO=hello@criloxsolutions.com" in env


def test_new_shell_assets_force_cache_refresh() -> None:
    sw = source("web/platform_app/service-worker.js")
    assert "signalrank-shell-v39" in sw
