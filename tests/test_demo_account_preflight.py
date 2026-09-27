from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from services import demo_certification


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
        html.index('id="brokerPolicyEditor"')
    ]
    assert "Enable execution" not in panel
    assert "Place order" not in panel
    assert "Execute trade" not in panel


def test_metatrader_demo_onboarding_persists_provider_verification_and_reconciliation() -> None:
    registry = Path("services/broker_connections.py").read_text(encoding="utf-8")
    mt5 = Path("services/mt5_client.py").read_text(encoding="utf-8")
    verification = Path("services/broker_verification.py").read_text(encoding="utf-8")

    upsert = registry[
        registry.index("async def upsert_connection("):
        registry.index("async def set_execution_enabled(")
    ]
    assert "verified_at: datetime | None = None" in upsert
    assert "if verified_at is not None:" in upsert
    assert "row.verified_at = verified_at" in upsert
    assert "row.last_health_at = verified_at" in upsert
    assert 'textual "verified" status alone never manufactures verification' in upsert

    link = mt5[
        mt5.index("async def link_platform_metatrader_account("):
        mt5.index("async def create_platform_metatrader_secure_link(")
    ]
    assert "verified_at=verified_at" in link
    assert "datetime.now(timezone.utc).replace(tzinfo=None)" in link
    assert "refresh_platform_metatrader_reconciliation(" in link
    assert "execution_enabled=False" in link

    reconcile = mt5[
        mt5.index("async def refresh_platform_metatrader_reconciliation("):
        mt5.index("def _position_id_from_row(")
    ]
    assert "get_reconciliation_snapshot(" in reconcile
    assert 'status = "HEALTHY" if ready else "RECONCILING"' in reconcile
    assert "record_reconciliation(" in reconcile
    assert '"provider_reconciliation_pending"' in reconcile
    assert '"ledger_source_event_id"' in reconcile

    verify = verification[
        verification.index("async def verify_broker_connection_read_only("):
        verification.index("__all__ =")
    ]
    assert "verify_platform_metatrader_connection(" in verify
    assert "refresh_platform_metatrader_reconciliation(" in verify
    assert '"reconciliation": reconciliation' in verify

    # Linking and verification are proof-only onboarding operations.  They may
    # inspect account/position state but must never mutate broker positions.
    proof_only = link + reconcile + verify
    for forbidden in (
        "execute_trade(",
        "create_market_order(",
        "place_order(",
        "close_position(",
        "close_all_positions(",
        "update_stop_loss(",
    ):
        assert forbidden not in proof_only


def test_demo_onboarding_does_not_silently_grant_execution_permission() -> None:
    registry = Path("services/broker_connections.py").read_text(encoding="utf-8")
    mt5 = Path("services/mt5_client.py").read_text(encoding="utf-8")

    upsert = registry[
        registry.index("async def upsert_connection("):
        registry.index("async def set_execution_enabled(")
    ]
    link = mt5[
        mt5.index("async def link_platform_metatrader_account("):
        mt5.index("async def create_platform_metatrader_secure_link(")
    ]

    assert 'execution_permission="SIGNALS_ONLY"' in upsert
    assert "row.execution_enabled = False" in upsert
    assert "execution_enabled=False" in link
    assert "ASSISTED_EXECUTION" not in link
    assert "AUTO_EXECUTION" not in link


def test_demo_prepare_policy_only_tightens_and_is_manual() -> None:
    kwargs = demo_certification._bounded_demo_policy_kwargs(
        {
            "reset_timezone": "Africa/Lagos",
            "currency": "USD",
            "max_risk_per_trade_pct": "0.02",
            "max_daily_loss_pct": "0.10",
            "max_weekly_loss_pct": "0.20",
            "max_total_drawdown_pct": "0.30",
            "max_open_positions": 8,
            "max_leverage": "50",
            "max_spread_bps": "200",
            "max_slippage_bps": "100",
            "min_confidence": "0.60",
            "min_expected_rr": "1.5",
            "allowed_instruments": ["EURUSD"],
            "allowed_asset_classes": ["FX"],
            "allowed_strategies": ["TREND"],
            "trading_windows": [{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "17:00"}],
        }
    )

    assert kwargs["account_mode"] == "DEMO"
    assert kwargs["execution_permission"] == "MANUAL"
    assert kwargs["max_risk_per_trade_pct"] == Decimal("0.005")
    assert kwargs["max_daily_loss_pct"] == Decimal("0.02")
    assert kwargs["max_weekly_loss_pct"] == Decimal("0.04")
    assert kwargs["max_total_drawdown_pct"] == Decimal("0.06")
    assert kwargs["max_open_positions"] == 1
    assert kwargs["max_leverage"] == Decimal("3")
    assert kwargs["max_spread_bps"] == Decimal("50")
    assert kwargs["max_slippage_bps"] == Decimal("25")
    assert kwargs["news_trading_allowed"] is False
    assert kwargs["weekend_holding_allowed"] is False
    assert kwargs["prop_firm"] is None
    assert kwargs["prop_rules_version"] is None
    assert kwargs["external_rules"] == {}


def test_demo_prepare_requires_provider_proven_demo_identity() -> None:
    with pytest.raises(PermissionError, match="provider_proven_demo_account_required"):
        demo_certification._assert_provider_demo_identity(
            {"environment": "live", "account_classification": "DEMO"}
        )
    with pytest.raises(PermissionError, match="provider_proven_demo_account_required"):
        demo_certification._assert_provider_demo_identity(
            {"environment": "demo", "account_classification": "LIVE_PERSONAL"}
        )

    demo_certification._assert_provider_demo_identity(
        {"environment": "demo", "account_classification": "DEMO"}
    )


def test_demo_prepare_requires_canonical_credential_state() -> None:
    assert demo_certification._credential_ready(
        {
            "credential_format": "envelope_v1",
            "credential_encrypted": True,
        }
    )
    assert demo_certification._credential_ready(
        {
            "credential_format": "provider_managed",
            "external_account_id": "provider-account",
        }
    )
    assert not demo_certification._credential_ready(
        {
            "credential_format": "envelope_v1",
            "credential_encrypted": False,
        }
    )
    assert not demo_certification._credential_ready(
        {
            "credential_format": "none",
            "credential_encrypted": False,
        }
    )


@pytest.mark.asyncio
async def test_demo_prepare_runs_read_only_proof_before_policy_and_never_enables_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    connection = {
        "connection_id": "demo-1",
        "environment": "demo",
        "account_classification": "DEMO",
        "credential_format": "envelope_v1",
        "credential_encrypted": True,
        "verified_at": "2026-09-27T12:00:00",
        "execution_enabled": False,
    }

    async def fake_connections(user_id: int):
        calls.append("connections")
        return [dict(connection)]

    async def fake_verify(user_id: int, connection_id: str):
        calls.append("verify")
        return {
            "success": True,
            "reconciliation": {
                "status": "HEALTHY",
                "ready": True,
            },
        }

    async def fake_policy(user_id: int, connection_id: str):
        calls.append("policy")
        return {
            "account_mode": "DEMO",
            "execution_permission": "SIGNALS_ONLY",
            "currency": "USD",
            "reset_timezone": "UTC",
            "max_risk_per_trade_pct": "0.005",
            "max_daily_loss_pct": "0.02",
            "max_weekly_loss_pct": "0.04",
            "max_total_drawdown_pct": "0.06",
            "max_open_positions": 3,
            "max_leverage": "1",
            "max_spread_bps": "50",
            "max_slippage_bps": "25",
            "min_confidence": "0",
            "min_expected_rr": "0",
        }

    async def fake_configure(user_id: int, connection_id: str, **kwargs):
        calls.append("configure")
        assert kwargs["account_mode"] == "DEMO"
        assert kwargs["execution_permission"] == "MANUAL"
        return {"policy_version": 2, **kwargs}

    monkeypatch.setattr(demo_certification, "_connections", fake_connections)
    monkeypatch.setattr(demo_certification, "_verify", fake_verify)
    monkeypatch.setattr(demo_certification, "_policy", fake_policy)
    monkeypatch.setattr(demo_certification, "_configure", fake_configure)

    result = await demo_certification.prepare_demo_certification(7, "demo-1")

    assert calls.index("verify") < calls.index("configure")
    assert result["demo_certification_prepared"] is True
    assert result["execution_permission"] == "MANUAL"
    assert result["execution_enabled"] is False
    assert result["order_placed"] is False
    assert result["connection"]["execution_enabled"] is False


def test_demo_prepare_web_action_is_explicit_and_never_claims_execution() -> None:
    service = Path("services/demo_certification.py").read_text(encoding="utf-8")
    api = Path("web/platform_api.py").read_text(encoding="utf-8")
    app = Path("web/platform_app/app.js").read_text(encoding="utf-8")

    assert "@router.post(\"/broker/connections/{connection_id}/demo-certification/prepare\")" in api
    assert "DemoCertificationPrepareRequest" in api
    assert "Explicit confirmation is required" in api
    assert '\"explicit_enable_still_required\": True' in api
    assert '\"live_activation_changed\": False' in api

    assert 'data-action="demo_prepare"' in app
    assert "Prepare DEMO certification" in app
    assert "keep execution OFF" in app
    assert "/demo-certification/prepare" in app

    assert "_assert_provider_demo_identity(connection)" in service
    assert "_credential_ready(refreshed)" in service
    assert 'str(reconciliation.get("status") or "").strip().upper() != "HEALTHY"' in service
    assert '"execution_permission": "MANUAL"' in service
    assert '"execution_enabled": False' in service
    assert '"order_placed": False' in service
    assert "set_execution_enabled" not in service

    for forbidden in (
        "execute_trade(",
        "create_market_order(",
        "place_order(",
        "close_position(",
        "close_all_positions(",
        "update_stop_loss(",
    ):
        assert forbidden not in service
