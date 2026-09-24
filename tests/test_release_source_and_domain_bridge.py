from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_source_gate():
    path = ROOT / "scripts" / "assert_release_source.py"
    spec = importlib.util.spec_from_file_location("assert_release_source", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_source_gate_passes_exact_railway_source(monkeypatch) -> None:
    gate = _load_source_gate()
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "SignalRankAI")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "fix/provider-discovery-readiness-20260923")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("EXPECTED_RELEASE_BRANCH", "fix/provider-discovery-readiness-20260923")
    monkeypatch.setenv("EXPECTED_RELEASE_COMMIT", "a" * 40)
    assert gate.validate_release_source() == []


def test_release_source_gate_blocks_wrong_production_branch(monkeypatch) -> None:
    gate = _load_source_gate()
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "SignalRankAI")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "fix/provider-discovery-readiness-20260923")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "b" * 40)
    monkeypatch.setenv("EXPECTED_RELEASE_BRANCH", "main")
    monkeypatch.setenv("EXPECTED_RELEASE_COMMIT", "b" * 40)
    errors = gate.validate_release_source()
    assert errors
    assert "does not match main" in errors[0]


def test_release_source_gate_blocks_wrong_commit(monkeypatch) -> None:
    gate = _load_source_gate()
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "SignalRankAI")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "c" * 40)
    monkeypatch.setenv("EXPECTED_RELEASE_BRANCH", "main")
    monkeypatch.setenv("EXPECTED_RELEASE_COMMIT", "d" * 40)
    errors = gate.validate_release_source()
    assert any("runtime commit" in item for item in errors)


def test_startup_bridge_is_frontdoor_only_and_opt_in() -> None:
    source = (ROOT / "start.sh").read_text(encoding="utf-8")
    frontdoor = source[source.index("_start_frontdoor()"):source.index("_start_monolith()")]
    assert "CUSTOM_DOMAIN_PORT_BRIDGE_ENABLED" in frontdoor
    assert "scripts/tcp_port_bridge.py" in frontdoor
    assert "--listen-port" in frontdoor
    assert "--target-port" in frontdoor
    monolith = source[source.index("_start_monolith()"):source.index("_on_railway=")]
    assert "tcp_port_bridge.py" not in monolith


def test_tcp_port_bridge_compiles() -> None:
    source = (ROOT / "scripts" / "tcp_port_bridge.py").read_text(encoding="utf-8")
    compile(source, "scripts/tcp_port_bridge.py", "exec")


def test_startup_requires_auth_secret_for_web_roles() -> None:
    source = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "_require_web_auth_secret()" in source
    assert "APP_AUTH_SECRET must be configured with at least 32 random characters" in source
    frontdoor = source[source.index("_start_frontdoor()"):source.index("_start_monolith()")]
    monolith = source[source.index("_start_monolith()"):source.index("_on_railway=")]
    assert "_require_web_auth_secret" in frontdoor
    assert "_require_web_auth_secret" in monolith


def test_platform_theme_and_brand_contract() -> None:
    html = (ROOT / "web" / "platform_app" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "platform_app" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "web" / "platform_app" / "app.js").read_text(encoding="utf-8")
    icon = (ROOT / "web" / "platform_app" / "icon.svg").read_text(encoding="utf-8")
    assert 'id="themeToggle"' in html
    assert '/app-assets/icon.svg' in html
    assert ':root[data-theme="light"]' in css
    assert "prefers-color-scheme:light" in css
    assert "signalrank.theme" in js
    assert "Switch to" in js
    assert "linearGradient" in icon
    assert "SignalRank" in icon
