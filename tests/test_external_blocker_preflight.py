from __future__ import annotations

from scripts.external_blocker_preflight import (
    marketplace_preflight,
    provider_preflight,
    scale_preflight,
)


def test_provider_preflight_blocks_missing_secret_and_external_evidence() -> None:
    result = provider_preflight("fmp", {}, environ={"FMP_ENABLED": "0"})
    assert result["status"] == "BLOCKED"
    assert result["activation_performed"] is False
    assert "required_provider_secret_missing" in result["blockers"]
    assert any(item.startswith("provider_external_evidence_missing:") for item in result["blockers"])


def test_provider_preflight_can_be_eligible_without_activating_provider() -> None:
    result = provider_preflight(
        "fmp",
        {
            "entitlement_approved": True,
            "redistribution_rights_approved": True,
            "live_market_data_certified": True,
        },
        environ={"FMP_ENABLED": "0", "FMP_API_KEY": "present-but-never-returned"},
    )
    assert result["status"] == "ELIGIBLE"
    assert result["claim_allowed"] is True
    assert result["activation_performed"] is False
    assert "present-but-never-returned" not in str(result)


def test_provider_preflight_rejects_gate_already_enabled() -> None:
    result = provider_preflight(
        "alphavantage",
        {
            "entitlement_approved": True,
            "request_budget_approved": True,
            "redistribution_rights_approved": True,
            "live_market_data_certified": True,
        },
        environ={"ALPHAVANTAGE_ENABLED": "1", "ALPHAVANTAGE_API_KEY": "secret"},
    )
    assert result["status"] == "BLOCKED"
    assert "provider_gate_must_remain_off_during_preflight" in result["blockers"]


def test_oanda_execution_request_requires_execution_and_reconciliation_evidence() -> None:
    result = provider_preflight(
        "oanda",
        {
            "intended_environment_approved": True,
            "market_data_certified": True,
            "regional_access_approved": True,
            "execution_requested": True,
        },
        environ={
            "OANDA_ENABLED": "0",
            "OANDA_LIVE_EXECUTION_ENABLED": "0",
            "OANDA_API_KEY": "secret",
            "OANDA_ACCOUNT_ID": "account",
        },
    )
    assert result["status"] == "BLOCKED"
    assert any(item.startswith("oanda_execution_evidence_missing:") for item in result["blockers"])


def test_scale_preflight_requires_exact_large_scale_pass_and_claim() -> None:
    eligible = scale_preflight(
        {
            "kind": "signalrank_scale_certification",
            "profile": "large_scale",
            "status": "PASS",
            "claim_allowed": True,
            "concurrency": {"actual": 20000, "required": 20000, "passed": True},
            "load_summary": {"configured_total_concurrency": 20000},
        }
    )
    assert eligible["status"] == "ELIGIBLE"
    assert eligible["capacity_claim_allowed"] is True
    assert eligible["activation_performed"] is False

    blocked = scale_preflight(
        {
            "kind": "signalrank_scale_certification",
            "profile": "public_beta",
            "status": "PASS",
            "claim_allowed": True,
            "concurrency": {"actual": 1500},
            "load_summary": {"configured_total_concurrency": 1500},
        }
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["capacity_claim_allowed"] is False


def test_marketplace_preflight_requires_all_external_and_runtime_approvals() -> None:
    blocked = marketplace_preflight({}, environ={
        "COPY_MARKETPLACE_ENABLED": "0",
        "COPY_TRADE_ENABLED": "0",
    })
    assert blocked["status"] == "BLOCKED"
    assert blocked["activation_performed"] is False

    evidence = {
        "publisher_identity_review": True,
        "follower_consent_and_revocation": True,
        "suitability_review": True,
        "transparent_performance_disclosure": True,
        "abuse_controls_review": True,
        "jurisdiction_approval": True,
        "commercial_terms_approval": True,
        "copy_execution_certified": True,
        "account_risk_certified": True,
        "duplicate_order_protection_certified": True,
        "kill_switch_certified": True,
    }
    eligible = marketplace_preflight(
        evidence,
        environ={"COPY_MARKETPLACE_ENABLED": "0", "COPY_TRADE_ENABLED": "0"},
    )
    assert eligible["status"] == "ELIGIBLE"
    assert eligible["public_marketplace_claim_allowed"] is True
    assert eligible["activation_performed"] is False


def test_marketplace_preflight_blocks_if_activation_gate_is_already_on() -> None:
    evidence = {
        "publisher_identity_review": True,
        "follower_consent_and_revocation": True,
        "suitability_review": True,
        "transparent_performance_disclosure": True,
        "abuse_controls_review": True,
        "jurisdiction_approval": True,
        "commercial_terms_approval": True,
        "copy_execution_certified": True,
        "account_risk_certified": True,
        "duplicate_order_protection_certified": True,
        "kill_switch_certified": True,
    }
    result = marketplace_preflight(
        evidence,
        environ={"COPY_MARKETPLACE_ENABLED": "1", "COPY_TRADE_ENABLED": "0"},
    )
    assert result["status"] == "BLOCKED"
    assert "marketplace_activation_gate_must_remain_off_during_preflight" in result["blockers"]
