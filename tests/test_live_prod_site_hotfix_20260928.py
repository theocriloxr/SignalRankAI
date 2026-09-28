from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_hotfix_restores_session_before_showing_login() -> None:
    html = source("web/platform_app/index.html")
    js = source("web/platform_app/app.js")
    assert 'id="bootstrapShell"' in html
    assert 'id="authShell" class="auth-shell" hidden' in html
    assert "refreshBrowserSession" in js
    assert "response.status===401" in js
    assert "showBootstrapError" in js
    assert "return request(path,options,false)" in js


def test_live_hotfix_keeps_tier_gating_server_backed_and_hides_locked_nav() -> None:
    html = source("web/platform_app/index.html")
    js = source("web/platform_app/app.js")
    policy = source("core/tier_policy.py")
    assert 'data-feature="paper_trading"' in html
    assert 'data-feature="portfolio_analytics"' in html
    assert 'data-feature="performance_analytics"' in html
    assert "document.querySelectorAll('[data-feature]')" in js
    assert "el.hidden=!allowed" in js
    assert '"broker_connection": Tier.PREMIUM' in policy


def test_live_hotfix_persists_and_reconciles_secure_metaapi_handoff() -> None:
    js = source("web/platform_app/app.js")
    mt5 = source("services/mt5_client.py")
    assert "SECURE_LINK_PENDING_KEY" in js
    assert "localStorage.setItem(SECURE_LINK_PENDING_KEY" in js
    assert "reconcilePendingSecureLink" in js
    assert "visibilitychange" in js
    assert "/broker/connections/" in js and "/verify" in js
    assert 'status="awaiting_credentials"' in mt5
    assert "external_account_id=account_id" in mt5
    assert "execution_enabled=False" in mt5


def test_live_hotfix_verifies_paystack_return_server_side() -> None:
    app = source("web/app.py")
    api = source("web/platform_api.py")
    js = source("web/platform_app/app.js")
    assert '@app.get("/billing/complete"' in app
    assert '@router.post("/billing/confirm")' in api
    assert "/transaction/verify/" in api
    assert 'paid_user_id != int(user["id"])' in api
    assert 'process_event({"event": "charge.success", "data": transaction})' in api
    assert "state.pendingBillingReference" in js
    assert "confirmPendingBillingReturn" in js


def test_live_hotfix_email_identity_and_readiness_routes() -> None:
    delivery = source("services/platform/email_delivery.py")
    app = source("web/app.py")
    assert "SignalRankAI <hello@criloxsolutions.com>" in delivery
    assert "EMAIL_REPLY_TO" in delivery
    assert '@app.get("/ready"' in app
    assert '@app.get("/readyz"' in app


def test_live_hotfix_has_no_single_selector_foreach_and_bumps_cache() -> None:
    js = source("web/platform_app/app.js")
    sw = source("web/platform_app/service-worker.js")
    import re
    assert re.search(r"(?<!\$)\$\([^)]*\)\.forEach", js) is None
    assert "signalrank-shell-v18" in sw
