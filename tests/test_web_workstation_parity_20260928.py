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
    assert '/app-assets/logo.svg' in html
    assert 'class="auth-brand-lockup"' in html
    assert "NAV_COLLAPSE_KEY='signalrank.nav.collapsed'" in app
    assert "function initNavToggle()" in app
    assert "document.body.classList.toggle('nav-collapsed'" in app
    assert "initNavToggle();" in app
    assert "body.nav-collapsed{--sidebar:78px}" in css
    assert "--brand-cyan:#05e8ff" in css
    assert "--brand-blue:#2f91ff" in css
    assert "--brand-purple:#b44cff" in css
    assert ':root[data-theme="light"]' in css
    assert "#05060a" in manifest
    assert "/app-assets/logo.svg" in worker
    for asset in (icon, logo):
        assert "#05E8FF" in asset
        assert "#2F91FF" in asset
        assert "#B44CFF" in asset
        assert "Signal Rank AI" in asset
