from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_exposes_full_canonical_command_catalog_without_telegram_menu_cap() -> None:
    api = source("web/platform_api.py")
    block = api[
        api.index('@router.get("/command-catalog")'):
        api.index('@router.get("/operator/overview")')
    ]
    assert "from signalrank_telegram.command_catalog import COMMANDS" in block
    assert "if tier_rank(spec.tier) > effective_rank" in block
    assert '"telegram_menu_limit": 100' in block
    assert "visible_commands(" not in block
    assert '"parity_model": "shared_services_same_entitlements"' in block


def test_command_catalog_routes_every_command_to_a_visible_web_workspace() -> None:
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    for marker in (
        'id="commandCatalog"',
        'id="commandSearch"',
        'id="commandCatalogCount"',
        'id="opsView"',
        'id="operatorCommandCatalog"',
        'id="opsNavButton"',
        'id="workspaceSearch"',
    ):
        assert marker in html
    assert "async function loadCommandCatalog()" in app
    assert "function renderCommandCatalog" in app
    assert "function activateWorkspaceSearch" in app
    assert "document.querySelectorAll('[data-view]')" in app
    assert "loaders={overview:loadOverview" in app
    for view in (
        '"signals": "signals"',
        '"proof": "evidence"',
        '"liveprice": "tools"',
        '"analyze": "tools"',
        '"connect_broker": "account"',
        '"paper_balance": "paper"',
        '"performance": "performance"',
    ):
        assert view in api


def test_operator_workspace_is_owner_admin_only_and_fail_safe() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    html = source("web/platform_app/index.html")
    block = api[
        api.index('@router.get("/operator/overview")'):
        api.index('@router.post("/auth/register"')
    ]
    assert 'authority not in {"OWNER", "ADMIN"}' in block
    assert "raise HTTPException(status_code=403" in block
    assert '"kill_switch": _env_bool("GLOBAL_EXECUTION_KILL_SWITCH", True)' in block
    assert '"real_execution_enabled": _env_bool("REAL_EXECUTION_ENABLED", False)' in block
    assert 'id="operatorRuntime"' in html
    assert 'id="operatorAi"' in html
    assert "async function loadOperator()" in app
    assert "opsButton.hidden=!authority" in app


def test_workstation_redesign_keeps_tier_gating_and_core_safety_copy() -> None:
    html = source("web/platform_app/index.html")
    css = source("web/platform_app/styles.css")
    app = source("web/platform_app/app.js")
    for marker in (
        'class="workspace-nav"',
        'class="nav-search-wrap"',
        'data-feature="paper_trading"',
        'data-feature="portfolio_analytics"',
        'data-feature="performance_analytics"',
        "Connection ≠ execution permission",
        "Only signals delivered to your account can execute",
        "Live activation remains separately gated",
    ):
        assert marker in html
    for marker in (
        "--sidebar:264px",
        ".workspace-nav",
        ".command-grid",
        ".command-card",
        ".bootstrap-shell",
        "@media(max-width:700px)",
        "@media(prefers-reduced-motion:reduce)",
    ):
        assert marker in css
    assert "el.hidden=!allowed" in app
    assert "Plan access never enables broker execution by itself." in app
