"""Production FastAPI-hosted SPA layout and PWA cache contract.

Read-only source tests: they never load credentials, issue orders or touch DB.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_UI = _ROOT / "web" / "platform_app"


def _read(name: str) -> str:
    return (_UI / name).read_text(encoding="utf-8")


def test_workstation_brand_has_single_canonical_emeral_silver_palette():
    css = _read("styles.css")
    assert "--brand-emerald:#4ce0a4" in css
    assert "--bg:#08120f" in css
    assert "--panel:#101e19" in css
    assert "--line:#294036" in css
    assert "--cyan:#4ce0a4" in css
    assert "--cyan:#08754e" in css
    assert ":root[data-theme=\"light\"]" in css
    assert "prefers-color-scheme:light" in css


def test_production_spa_view_controls_and_account_authority_preserved():
    html = _read("index.html")
    js = _read("app.js")
    for label in (
        'id="sessionNav"', 'id="viewSwitcher"', 'id="appShell"',
        'id="authShell"', 'id="opsNavButton"',
    ):
        assert label in html, label
    for key in ("function setLoggedIn", "function initNavToggle",
                "function syncThemeUi", "const API='/api/v1/platform'"):
        assert key in js, key


def test_mobile_safe_areas_and_keyboard_contrast_no_horizontal_viewport_risk():
    css = _read("styles.css")
    assert "2026-10-09 production workstation responsive polish" in css
    assert "safe-area-inset-top" in css
    assert "safe-area-inset-left" in css
    assert "safe-area-inset-right" in css
    assert "@media(max-width:390px)" in css
    assert ".card-grid,.mini-metrics{grid-template-columns:1fr}" in css
    assert "focus-visible{outline:3px solid var(--cyan)" in css
    assert "@media(forced-colors:active)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_offline_css_version_and_pwa_theme_are_consistent():
    html = _read("index.html")
    service_worker = _read("service-worker.js")
    manifest = _read("manifest.webmanifest")
    assert '/app-assets/styles.css?v=44' in html
    assert "'/app-assets/styles.css?v=44'" in service_worker
    assert "signalrank-shell-v44" in service_worker
    assert '"background_color": "#08120f"' in manifest
    assert '"theme_color": "#4ce0a4"' in manifest
    assert '<meta name="theme-color" content="#08120f"' in html
    assert 'src="/app-assets/app.js?v=43"' in html
    assert "url.pathname.startsWith('/api/')" in service_worker
