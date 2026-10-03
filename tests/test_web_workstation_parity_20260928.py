from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_exposes_shared_telegram_command_catalog() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    html = source("web/platform_app/index.html")

    assert '@router.get("/command-catalog")' in api
    assert "from signalrank_telegram.command_catalog import COMMANDS" in api
    assert "if tier_rank(spec.tier) > effective_rank" in api
    assert '"telegram_menu_limit": 100' in api
    assert '"parity_model": "shared_services_same_entitlements"' in api
    assert 'id="commandCatalog"' in html
    assert 'id="commandSearch"' in html
    assert "async function loadCommandCatalog()" in app
    assert "renderCommandCatalog" in app
    assert "loadCommandCatalog()" in app[app.index("async function boot()"):app.index("async function loadOverview()")]


def test_operator_workspace_is_authority_gated_and_not_public() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    html = source("web/platform_app/index.html")

    block = api[api.index('@router.get("/operator/overview")'):api.index('@router.post("/auth/register"')]
    assert '_platform_operator_authority(user)' in block
    assert 'authority not in {"OWNER", "ADMIN"}' in block
    assert 'id="opsNavButton"' in html and "hidden" in html[html.index('id="opsNavButton"'):html.index('id="opsNavButton"') + 200]
    assert 'id="opsView"' in html
    assert "async function loadOperator()" in app


def test_workstation_redesign_preserves_all_primary_views() -> None:
    html = source("web/platform_app/index.html")
    css = source("web/platform_app/styles.css")
    for view in (
        "overview", "signals", "evidence", "markets", "tools", "paper",
        "portfolio", "performance", "journal", "support", "account", "ops",
    ):
        assert f'id="{view}View"' in html
    for marker in (
        "--sidebar:", ".workspace-nav", ".command-catalog", ".broker-account-grid",
        ".evidence-workspace", "@media(max-width:900px)", "@media(max-width:480px)",
    ):
        assert marker in css
    assert "position:fixed" in css[css.index(".topbar"):css.index(".brand{")]


def test_workspace_search_and_command_jump_are_keyboard_accessible() -> None:
    app = source("web/platform_app/app.js")
    html = source("web/platform_app/index.html")
    assert 'id="workspaceSearch"' in html
    assert "activateWorkspaceSearch" in app
    assert "(e.ctrlKey||e.metaKey)" in app
    assert "String(e.key).toLowerCase()==='k'" in app


def test_all_launch_command_sections_have_web_destination() -> None:
    api = source("web/platform_api.py")
    expected_sections = (
        "Getting started", "Account", "Signals", "Market", "Preferences",
        "Paper trading", "Referrals", "Support", "Analytics", "Broker",
        "VIP analytics", "VIP controls", "VIP signals", "Admin", "Adaptive",
        "Owner", "Admin diagnostics", "Owner diagnostics",
    )
    route = api[api.index('@router.get("/command-catalog")'):api.index('@router.get("/operator/overview")')]
    for section in expected_sections:
        assert f'"{section}"' in route


def test_brand_sidebar_and_theme_follow_signal_rank_logo_contract() -> None:
    html = source("web/platform_app/index.html")
    css = source("web/platform_app/styles.css")
    app = source("web/platform_app/app.js")
    icon = source("web/platform_app/icon.svg")
    logo = source("web/platform_app/logo.svg")
    manifest = source("web/platform_app/manifest.webmanifest")
    worker = source("web/platform_app/service-worker.js")

    assert 'id="navToggle"' in html
    assert 'id="navToggleIcon"' in html
    assert 'id="navReopen"' in html
    assert '/app-assets/icon.svg' in html
    assert '/app-assets/logo.svg' in html
    assert 'class="auth-brand-lockup"' in html
    assert "NAV_COLLAPSE_KEY='signalrank.nav.collapsed'" in app
    assert "function initNavToggle()" in app
    assert "$('#navReopen')?.addEventListener('click',()=>setNavCollapsed(false))" in app
    assert "document.body.classList.toggle('nav-collapsed'" in app
    assert "initNavToggle();" in app
    assert "body.session-active.nav-collapsed{--sidebar:0px}" in css
    assert "transform:translateX(calc(-100% - 20px))" in css
    assert "--brand-emerald:#00e88f" in css
    assert "--brand-silver:#dfe7e2" in css
    assert "--brand-gradient:linear-gradient" in css
    assert ':root[data-theme="light"]' in css
    assert "#00a96e" in manifest
    assert "signalrank-shell-v40" in worker
    assert "/app-assets/icon.svg" in worker
    assert "/app-assets/logo.svg" in worker
    for asset in (icon, logo):
        assert "data:image/webp;base64," in asset
        assert "Signal Rank AI" in asset


def test_account_aware_bootstrap_retries_and_routes_by_authority_and_tier() -> None:
    app = source("web/platform_app/app.js")

    assert "async function requestWithRetry(" in app
    assert "requestWithRetry('/me'" in app
    assert "requestWithRetry('/entitlements'" in app
    assert "function accountLandingView()" in app
    assert "if(authority==='OWNER'||authority==='ADMIN')return 'ops'" in app
    assert "if((tier==='institutional'||tier==='professional')&&hasFeature('performance_analytics'))return 'performance'" in app
    assert "if(tier==='vip'||tier==='premium')return 'signals'" in app
    assert "return 'overview'" in app
    assert "showView(landing)" in app
    assert "Reconnecting to SignalRank" in app
    assert "bootstrapRetryTimer=setTimeout" in app

def test_market_explorer_exposes_broader_research_classes_without_execution_claim() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    for marker in (
        'id="assetClassFilter"',
        'id="instrumentTypeFilter"',
        '<option value="etf">ETFs</option>',
        '<option value="option">Options · research</option>',
        '<option value="future">Futures · research</option>',
        '<option value="bond">Bonds · research</option>',
        '<option value="perpetual">Perpetual</option>',
        '<option value="dated_future">Dated future</option>',
    ):
        assert marker in html
    assert "instrumentType=$('#instrumentTypeFilter')?.value" in app
    assert "qs.set('instrument_type',instrumentType)" in app
    assert 'instrument_type: str | None = Query(default=None, max_length=32)' in api
    assert "Analysis only" in app


def test_account_identity_is_authoritative_and_safe_reads_self_heal() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")

    me = api[api.index('@router.get("/me")'):api.index('@router.get("/entitlements")')]
    assert 'payload["authority"] = authority' in me
    assert 'payload["default_workspace"] = default_workspace' in me
    assert 'authority in {"OWNER", "ADMIN"}' in me
    assert 'default_workspace = "ops"' in me
    assert 'default_workspace = "performance"' in me
    assert 'default_workspace = "signals"' in me
    assert 'default_workspace = "overview"' in me

    assert "const safeRead=method==='GET'||method==='HEAD'" in app
    assert "[502,503,504].includes(response.status)" in app
    assert "transientAttempt<2" in app
    assert "state.user?.default_workspace" in app
    assert "const canOperate=authority==='OWNER'||authority==='ADMIN'" in app
    assert "SignalRank services are temporarily unavailable" not in app


def test_pwa_brand_shell_updates_existing_clients_immediately() -> None:
    worker = source("web/platform_app/service-worker.js")
    html = source("web/platform_app/index.html")
    assert "self.skipWaiting()" in worker
    assert "self.clients.claim()" in worker
    assert "styles.css?v=38" in html
    assert "app.js?v=38" in html
    assert "icon.svg?v=38" in html
    assert "logo.svg?v=38" in html
