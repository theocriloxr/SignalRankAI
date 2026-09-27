from __future__ import annotations

from pathlib import Path


def test_demo_preflight_is_counts_only_staging_read_only() -> None:
    source = Path("scripts/demo_account_preflight.py").read_text(encoding="utf-8")

    assert "demo_account_preflight_requires_staging" in source
    assert "Path(__file__).resolve().parents[1]" in source
    assert "sys.path.insert(0, str(ROOT))" in source
    assert "SELECT version_num FROM alembic_version" in source
    assert "UPPER(COALESCE(p.account_mode, '')) = 'DEMO'" in source
    assert "UPPER(COALESCE(r.status, '')) = 'HEALTHY'" in source
    assert "credential_format" in source
    assert "activation_performed" in source
    assert '"orders_placed": 0' in source
    assert '"secrets_returned": False' in source

    lowered = source.lower()
    assert "place_order(" not in lowered
    assert "submit_order(" not in lowered
    assert "create_market_order(" not in lowered
    assert "external_account_id" not in source
    assert "account_ref" not in source
    assert "secret_encrypted" not in source
    assert "password_encrypted" not in source


def test_demo_preflight_blockers_are_explicit() -> None:
    source = Path("scripts/demo_account_preflight.py").read_text(encoding="utf-8")
    for blocker in (
        "demo_account_not_connected",
        "demo_account_not_read_only_verified",
        "demo_account_credentials_not_ready",
        "demo_reconciliation_not_healthy",
        "demo_policy_frozen",
        "demo_execution_permission_not_configured",
        "demo_execution_already_enabled_review_required",
    ):
        assert blocker in source


def test_web_demo_certification_readiness_is_read_only_and_canonical() -> None:
    api = Path("web/platform_api.py").read_text(encoding="utf-8")
    html = Path("web/platform_app/index.html").read_text(encoding="utf-8")
    app = Path("web/platform_app/app.js").read_text(encoding="utf-8")

    for marker in (
        '"demo_certification"',
        '"connected_demo_accounts"',
        '"preflight_ready_accounts"',
        '"bounded_lifecycle_ready_accounts"',
        '"execution_disabled_for_preflight"',
        '"orders_placed_by_readiness_check": 0',
        '"activation_performed": False',
        '"bounded_demo_lifecycle_required": True',
        '"certification_report_required_for_live_activation": True',
    ):
        assert marker in api

    for blocker in (
        "demo_account_not_read_only_verified",
        "demo_account_credentials_not_ready",
        "demo_policy_not_configured",
        "demo_execution_permission_not_configured",
        "demo_reconciliation_not_healthy",
        "demo_policy_frozen",
        "demo_execution_already_enabled_review_required",
    ):
        assert blocker in api

    assert 'id="demoCertificationPanel"' in html
    assert 'id="demoCertificationAccounts"' in html
    assert 'id="demoCertificationConnect"' in html
    assert "data.demo_certification||{}" in app
    assert "Execution OFF for preflight" in app
    assert "bounded demo order/modify/close/reconciliation lifecycle" in app

    panel = html[
        html.index('id="demoCertificationPanel"'):
        html.index('id="brokerPolicyEditor"'),
    ]
    assert "Enable execution" not in panel
    assert "Place order" not in panel
    assert "Execute trade" not in panel
