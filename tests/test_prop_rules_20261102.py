"""Prop presets and worst-case headroom (2 Nov 2026)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from core.account_policy import AccountRiskSnapshot, TradingAccountPolicy, evaluate_account_policy
from core.prop_rules import PROP_PRESETS, PropAccountState, evaluate_headroom, floors, open_risk_amount, preset

MONDAY_NOON = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _state(**kw):
    base = dict(initial_balance=100000, day_start_balance=100000, current_equity=100000,
                highest_eod_balance=100000, open_risk_amount=0, evaluated_at_utc=MONDAY_NOON)
    base.update(kw)
    return PropAccountState(**base)


def test_ftmo_floors_static_from_initial_balance():
    rules = preset("ftmo_2step")
    daily, overall = floors(rules, _state(day_start_balance=103000))
    assert daily == D("98000")  # midnight balance 103k minus 5% of the 100k initial balance
    assert overall == D("90000")


def test_fundednext_daily_allowance_from_day_start_balance():
    daily, overall = floors(preset("fundednext_stellar_2step"), _state(day_start_balance=110000))
    assert daily == D("104500") and overall == D("90000")


def test_trailing_eod_floor_locks_at_initial_for_topstep():
    rules = preset("topstep_50k")
    s = _state(initial_balance=50000, day_start_balance=51000, current_equity=51000, highest_eod_balance=51000)
    assert floors(rules, s)[1] == D("49000")
    locked = _state(initial_balance=50000, day_start_balance=53000, current_equity=53000, highest_eod_balance=53000)
    assert floors(rules, locked)[1] == D("50000")


def test_worst_case_counts_open_positions():
    rules = preset("ftmo_2step")
    # down 3% today with 1% still at risk in open trades: floor 95k + 0.5% buffer leaves 500 of room
    s = _state(current_equity=97000, open_risk_amount=1000)
    blocked = evaluate_headroom(rules, s, proposed_risk_amount=1000)
    assert not blocked.allowed and "prop_worst_case_would_breach" in blocked.reasons
    assert blocked.room_amount == D("500")
    ok = evaluate_headroom(rules, s, proposed_risk_amount=400)
    assert ok.allowed and ok.max_new_risk_pct > 0


def test_floor_reached_and_open_risk_exhausted():
    rules = preset("ftmo_2step")
    at_floor = evaluate_headroom(rules, _state(current_equity=95400), proposed_risk_amount=100)
    assert "prop_daily_floor_reached" in at_floor.reasons
    exhausted = evaluate_headroom(rules, _state(current_equity=97000, open_risk_amount=1600), proposed_risk_amount=10)
    assert "prop_open_risk_uses_all_headroom" in exhausted.reasons


def test_unknown_order_risk_and_baseline_fail_closed():
    rules = preset("ftmo_2step")
    assert "prop_order_risk_unknown" in evaluate_headroom(rules, _state(), proposed_risk_amount=0).reasons
    assert evaluate_headroom(rules, _state(initial_balance=0), proposed_risk_amount=10).reasons == (
        "prop_baseline_unavailable",)


def test_topstep_flat_by_window_and_weekend():
    rules = preset("topstep_50k")
    near_close = datetime(2026, 11, 2, 20, 50, tzinfo=timezone.utc)  # 14:50 Chicago, 20 min before flat-by
    s = _state(initial_balance=50000, day_start_balance=50000, current_equity=50000, highest_eod_balance=50000,
               evaluated_at_utc=near_close)
    assert "prop_flat_by_window" in evaluate_headroom(rules, s, proposed_risk_amount=100).reasons
    after_close = datetime(2026, 11, 2, 21, 30, tzinfo=timezone.utc)  # 15:30 Chicago, market closed for the firm
    s2 = _state(initial_balance=50000, day_start_balance=50000, current_equity=50000, evaluated_at_utc=after_close)
    assert "prop_flat_by_window" in evaluate_headroom(rules, s2, proposed_risk_amount=100).reasons
    s3 = _state(initial_balance=50000, day_start_balance=50000, current_equity=50000)
    assert "prop_weekend_holding_forbidden" in evaluate_headroom(
        rules, s3, proposed_risk_amount=100, weekend_hold_expected=True).reasons


def test_funded_ftmo_news_and_weekend_rules_only_when_funded():
    rules = preset("ftmo_2step")
    challenge = evaluate_headroom(rules, _state(), proposed_risk_amount=100, high_impact_news_window=True,
                                  weekend_hold_expected=True)
    assert challenge.allowed
    funded = evaluate_headroom(rules, _state(), proposed_risk_amount=100, high_impact_news_window=True,
                               weekend_hold_expected=True, funded=True)
    assert {"prop_news_blackout", "prop_weekend_holding_forbidden"} <= set(funded.reasons)


def test_open_risk_from_positions():
    positions = [
        # long 1 lot: +$500 for +5.0 price -> $100/unit; stop 3 below current -> $300
        {"type": "POSITION_TYPE_BUY", "openPrice": 100, "currentPrice": 105, "stopLoss": 102, "profit": 500},
        # short with no stop -> charged the fallback 0.5% of 100k
        {"type": "POSITION_TYPE_SELL", "openPrice": 50, "currentPrice": 49, "stopLoss": 0, "profit": 100},
        # long with stop already in profit -> no risk
        {"type": "buy", "openPrice": 10, "currentPrice": 12, "stopLoss": 12.5, "profit": 200},
    ]
    amount, unknown = open_risk_amount(positions, equity=D("100000"), fallback_risk_pct=D("0.005"))
    assert amount == D("300") + D("500") and unknown == 1


def test_every_preset_has_a_floor_and_source():
    for name, rules in PROP_PRESETS.items():
        daily, overall = floors(rules, _state(initial_balance=100000))
        assert overall is not None, name
        assert rules["source"].startswith("https://") and rules["verified"]


def _policy(**kw):
    base = dict(connection_id="c1", user_id=1, account_mode="DEMO", execution_permission="AUTO_EXECUTION",
                status="active", max_risk_per_trade_pct=D("0.01"), max_daily_loss_pct=D("0.03"),
                max_total_drawdown_pct=D("0.06"), max_open_positions=5)
    base.update(kw)
    return TradingAccountPolicy(**base)


def _snapshot(**kw):
    base = dict(current_equity=D("97500"), day_start_equity=D("100000"), peak_equity=D("100000"),
                proposed_risk_pct=D("0.01"), account_is_demo=True, spread_bps=D("1"), expected_slippage_bps=D("1"),
                evaluated_at_utc=MONDAY_NOON)
    base.update(kw)
    return AccountRiskSnapshot(**base)


def test_generic_daily_headroom_includes_open_risk():
    # 2.5% down today, 3% limit: a 1% trade could take the day to 3.5%
    decision = evaluate_account_policy(_policy(), _snapshot(), execution_mode="auto")
    assert "daily_loss_headroom" in decision.reasons
    assert decision.max_allowed_risk_pct == D("0.005")
    with_open = evaluate_account_policy(_policy(), _snapshot(current_equity=D("99000"), open_risk_pct=D("0.015")),
                                        execution_mode="auto")
    assert "daily_loss_headroom" in with_open.reasons
    fine = evaluate_account_policy(_policy(), _snapshot(current_equity=D("100000")), execution_mode="auto")
    assert fine.allowed and fine.max_allowed_risk_pct == D("0.01")


def test_loss_streak_pause():
    policy = _policy(extra_rules={"max_consecutive_losses": 3})
    snap = _snapshot(current_equity=D("100000"), consecutive_losses=3)
    assert "loss_streak_pause" in evaluate_account_policy(policy, snap, execution_mode="auto").reasons


def test_prop_preset_rule_is_validated_and_enforced():
    with pytest.raises(ValueError):
        _policy(account_mode="PROP", extra_rules={"hard_rules": [{"id": "p", "type": "prop_preset",
                                                                  "preset": "nope"}]})
    policy = _policy(
        account_mode="PROP", certified=True, certification_ref="ref", prop_firm="FTMO", prop_rules_version="2026-06",
        external_max_daily_loss_pct=D("0.05"), external_max_total_drawdown_pct=D("0.10"),
        max_daily_loss_pct=D("0.05"), max_total_drawdown_pct=D("0.10"),
        extra_rules={"hard_rules": [{"id": "ftmo", "type": "prop_preset", "preset": "ftmo_2step",
                                     "initial_balance": "100000"}]},
    )
    snap = _snapshot(current_equity=D("96600"), day_start_equity=D("100000"), account_is_demo=False,
                     loss_baselines_verified=True, weekly_baseline_verified=True, open_risk_amount=D("500"))
    decision = evaluate_account_policy(policy, snap, execution_mode="auto")
    assert "prop_rule:ftmo:prop_worst_case_would_breach" in decision.reasons
    assert decision.prop_headroom and D(decision.prop_headroom["binding_floor"]) == D("95000")
    assert decision.max_allowed_risk_pct is not None and decision.max_allowed_risk_pct < D("0.01")


def test_policy_fields_from_preset_build_a_valid_prop_policy():
    from core.prop_rules import policy_fields_from_preset

    fields = policy_fields_from_preset("topstep_50k", initial_balance="50000")
    assert fields["external_max_total_drawdown_pct"] == D("0.0400")
    assert fields["weekend_holding_allowed"] is False
    policy = _policy(
        certified=True, certification_ref="r", max_risk_per_trade_pct=D("0.005"),
        **{k: v for k, v in fields.items() if k not in {"external_rules"}},
        extra_rules=fields["external_rules"],
    )
    assert policy.account_mode == "PROP" and policy.extra_rules["hard_rules"][0]["preset"] == "topstep_50k"
    funded = policy_fields_from_preset("ftmo_2step", initial_balance=100000, funded=True)
    assert funded["news_trading_allowed"] is False and funded["weekend_holding_allowed"] is False
    with pytest.raises(ValueError):
        policy_fields_from_preset("ftmo_2step", initial_balance=0)
