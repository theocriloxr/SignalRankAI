from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.account_policy import (
    AccountRiskSnapshot,
    TradingAccountPolicy,
    evaluate_account_policy,
)


def _snapshot(**overrides):
    values = {
        "current_equity": Decimal("10000"),
        "day_start_equity": Decimal("10000"),
        "peak_equity": Decimal("10000"),
        "daily_realized_pnl": Decimal("0"),
        "week_start_equity": Decimal("10000"),
        "weekly_realized_pnl": Decimal("0"),
        "open_positions": 0,
        "proposed_risk_pct": Decimal("0.005"),
        "proposed_leverage": Decimal("1"),
        "symbol": "EURUSD",
        "asset_class": "FX",
        "account_is_demo": True,
        "reconciliation_ready": True,
        "loss_baselines_verified": False,
        "weekly_baseline_verified": True,
    }
    values.update(overrides)
    return AccountRiskSnapshot(**values)


def _policy(**overrides):
    values = {
        "connection_id": "acct-1",
        "user_id": 10,
        "account_mode": "DEMO",
        "execution_permission": "AUTO_EXECUTION",
        "status": "configured",
        "max_risk_per_trade_pct": Decimal("0.01"),
        "max_daily_loss_pct": Decimal("0.04"),
        "max_total_drawdown_pct": Decimal("0.08"),
        "max_open_positions": 3,
        "max_leverage": Decimal("2"),
    }
    values.update(overrides)
    return TradingAccountPolicy(**values)


def test_demo_policy_can_allow_without_live_loss_baseline():
    decision = evaluate_account_policy(
        _policy(),
        _snapshot(),
        execution_mode="auto",
    )
    assert decision.allowed is True
    assert decision.reasons == ()


def test_paper_never_crosses_broker_boundary():
    decision = evaluate_account_policy(
        _policy(account_mode="PAPER"),
        _snapshot(account_is_demo=None),
        execution_mode="manual_confirmed",
    )
    assert decision.allowed is False
    assert "paper_account_broker_execution_forbidden" in decision.reasons


@pytest.mark.parametrize("mode", ["LIVE_PERSONAL", "PROP"])
def test_real_money_requires_verified_loss_baselines(mode):
    kwargs = {
        "account_mode": mode,
        "execution_permission": "AUTO_EXECUTION",
    }
    if mode == "PROP":
        kwargs.update(
            certified=True,
            certification_ref="cert-1",
            prop_firm="example",
            prop_rules_version="2026-09",
            external_max_daily_loss_pct=Decimal("0.05"),
            external_max_total_drawdown_pct=Decimal("0.10"),
        )
    decision = evaluate_account_policy(
        _policy(**kwargs),
        _snapshot(account_is_demo=False, loss_baselines_verified=False),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "loss_baseline_unavailable" in decision.reasons


def test_certified_prop_uses_conservative_internal_buffered_external_limit():
    policy = _policy(
        account_mode="PROP",
        certified=True,
        certification_ref="cert-7",
        prop_firm="example-prop",
        prop_rules_version="rules-v3",
        safety_buffer_pct=Decimal("0.01"),
        max_daily_loss_pct=Decimal("0.04"),
        max_total_drawdown_pct=Decimal("0.08"),
        external_max_daily_loss_pct=Decimal("0.05"),
        external_max_total_drawdown_pct=Decimal("0.10"),
    )
    snapshot = _snapshot(
        current_equity=Decimal("9650"),
        day_start_equity=Decimal("10000"),
        peak_equity=Decimal("10000"),
        account_is_demo=False,
        loss_baselines_verified=True,
    )
    decision = evaluate_account_policy(policy, snapshot, execution_mode="auto")
    assert decision.allowed is True
    assert decision.effective_daily_loss_limit == Decimal("0.04")
    assert decision.effective_drawdown_limit == Decimal("0.08")

    blocked = evaluate_account_policy(
        policy,
        _snapshot(
            current_equity=Decimal("9600"),
            day_start_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            account_is_demo=False,
            loss_baselines_verified=True,
        ),
        execution_mode="auto",
    )
    assert blocked.allowed is False
    assert "daily_loss_limit" in blocked.reasons


def test_prop_cannot_self_certify_by_only_supplying_limits():
    policy = _policy(
        account_mode="PROP",
        prop_firm="example-prop",
        prop_rules_version="rules-v3",
        external_max_daily_loss_pct=Decimal("0.05"),
        external_max_total_drawdown_pct=Decimal("0.10"),
    )
    decision = evaluate_account_policy(
        policy,
        _snapshot(account_is_demo=False, loss_baselines_verified=True),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "prop_policy_not_certified" in decision.reasons


def test_reconciliation_discrepancy_blocks_new_risk():
    decision = evaluate_account_policy(
        _policy(),
        _snapshot(reconciliation_ready=False),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "account_reconciliation_unready" in decision.reasons


def test_assisted_permission_cannot_auto_trade():
    decision = evaluate_account_policy(
        _policy(execution_permission="ASSISTED_EXECUTION"),
        _snapshot(),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "execution_permission_blocked" in decision.reasons

    manual = evaluate_account_policy(
        _policy(execution_permission="ASSISTED_EXECUTION"),
        _snapshot(),
        execution_mode="manual_confirmed",
    )
    assert manual.allowed is True


def test_account_policy_is_account_specific():
    a = _policy(connection_id="personal", max_risk_per_trade_pct=Decimal("0.01"))
    b = _policy(connection_id="prop", max_risk_per_trade_pct=Decimal("0.0025"))
    snapshot = _snapshot(proposed_risk_pct=Decimal("0.005"))
    assert evaluate_account_policy(a, snapshot, execution_mode="auto").allowed
    decision = evaluate_account_policy(b, snapshot, execution_mode="auto")
    assert not decision.allowed
    assert "risk_per_trade_limit" in decision.reasons


def test_invalid_timezone_is_rejected():
    with pytest.raises(ValueError, match="invalid_reset_timezone"):
        _policy(reset_timezone="Definitely/Not-A-Timezone")


def test_execution_claims_are_isolated_by_trading_account():
    from core.execution_claims import execution_claim_key

    first = execution_claim_key(10, "sig-1", account_scope="broker:personal")
    same = execution_claim_key(10, "sig-1", account_scope="broker:personal")
    second = execution_claim_key(10, "sig-1", account_scope="broker:prop-01")
    paper = execution_claim_key(10, "sig-1", account_scope="paper:10")

    assert first == same
    assert len({first, second, paper}) == 3


def test_execution_evidence_api_accepts_account_scope():
    import inspect
    from services.execution_evidence import (
        get_execution_evidence,
        get_platform_execution_evidence,
    )

    assert "connection_id" in inspect.signature(get_execution_evidence).parameters
    assert "connection_id" in inspect.signature(get_platform_execution_evidence).parameters


def test_live_account_requires_weekly_baseline_when_weekly_limit_is_enabled():
    decision = evaluate_account_policy(
        _policy(account_mode="LIVE_PERSONAL"),
        _snapshot(
            account_is_demo=False,
            loss_baselines_verified=True,
            weekly_baseline_verified=False,
            week_start_equity=Decimal("0"),
        ),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "weekly_loss_baseline_unavailable" in decision.reasons


def test_weekly_loss_limit_is_enforced():
    decision = evaluate_account_policy(
        _policy(
            account_mode="LIVE_PERSONAL",
            max_weekly_loss_pct=Decimal("0.05"),
        ),
        _snapshot(
            account_is_demo=False,
            current_equity=Decimal("9499"),
            day_start_equity=Decimal("9500"),
            week_start_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            loss_baselines_verified=True,
            weekly_baseline_verified=True,
        ),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert "weekly_loss_limit" in decision.reasons
    assert decision.effective_weekly_loss_limit == Decimal("0.05")


@pytest.mark.parametrize(
    "snapshot_overrides,policy_overrides,reason",
    [
        ({"spread_bps": Decimal("21")}, {"max_spread_bps": Decimal("20")}, "spread_limit"),
        ({"expected_slippage_bps": Decimal("11")}, {"max_slippage_bps": Decimal("10")}, "slippage_limit"),
        ({"confidence": Decimal("0.69")}, {"min_confidence": Decimal("0.70")}, "confidence_below_minimum"),
        ({"expected_rr": Decimal("1.49")}, {"min_expected_rr": Decimal("1.50")}, "reward_risk_below_minimum"),
        ({"strategy": "momentum"}, {"allowed_strategies": ("trend",)}, "strategy_not_allowed"),
    ],
)
def test_account_quality_constraints_fail_closed(snapshot_overrides, policy_overrides, reason):
    decision = evaluate_account_policy(
        _policy(**policy_overrides),
        _snapshot(**snapshot_overrides),
        execution_mode="auto",
    )
    assert decision.allowed is False
    assert reason in decision.reasons


def test_account_trading_window_uses_policy_timezone():
    policy = _policy(
        reset_timezone="Africa/Lagos",
        trading_windows=(
            {"days": [0], "start": "09:00", "end": "10:00"},
        ),
    )
    inside = _snapshot(
        evaluated_at_utc=datetime(2026, 9, 28, 8, 30, tzinfo=timezone.utc)
    )
    outside = _snapshot(
        evaluated_at_utc=datetime(2026, 9, 28, 10, 30, tzinfo=timezone.utc)
    )
    assert evaluate_account_policy(policy, inside, execution_mode="auto").allowed
    denied = evaluate_account_policy(policy, outside, execution_mode="auto")
    assert not denied.allowed
    assert "outside_trading_window" in denied.reasons


def test_invalid_confidence_policy_is_rejected():
    with pytest.raises(ValueError, match="min_confidence_must_not_exceed_one"):
        _policy(min_confidence=Decimal("1.01"))
