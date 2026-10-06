"""Primary signal sizing must preserve the configured loss and notional limits."""
import math
from datetime import timedelta
from types import SimpleNamespace

import pytest

from core.tier_constants import DD_HARD_LIMIT
from engine import risk, risk_manager
from utils.timeutils import now_utc_naive


@pytest.fixture(autouse=True)
def fixed_advice_policy(monkeypatch):
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.5")
    monkeypatch.setenv("EXPECTANCY_BOOST_BASE", "0.5")
    monkeypatch.setenv("EXPECTANCY_BOOST_RANGE", "0.5")
    monkeypatch.setenv("ML_RISK_BASE", "0.5")
    monkeypatch.setenv("ML_RISK_RANGE", "0.5")
    monkeypatch.setattr(risk_manager, "BASE_RISK_PCT", 0.5)


def signal(**overrides):
    return {"asset": "BTCUSDT", "asset_class": "crypto", "direction": "long", "entry": 100.0,
            "stop_loss": 95.0, **overrides}


@pytest.mark.parametrize("state", [SimpleNamespace(drawdown=DD_HARD_LIMIT), {"drawdown": DD_HARD_LIMIT},
                                  {"drawdown": float("nan")}, {}, {"drawdown": True}])
def test_primary_and_manager_advice_share_fail_closed_account_boundaries(state):
    item = signal()
    profile = risk.calculate_dynamic_risk(item, account_state=state)
    assert profile["risk_pct"] == risk_manager.RiskManager(10_000).get_dynamic_risk_pct(item, state) == 0
    assert profile["hard_stop"] and risk.hard_stop_active(state)
    item["risk_profile"] = profile
    assert risk.calculate_position_size(item, 10_000) == 0


@pytest.mark.parametrize("regime", ["neutral", "trending", "ranging"])
def test_heuristic_and_raw_model_scores_cannot_become_probability_or_raise_the_budget(regime):
    plain = signal(regime=regime)
    boosted = signal(regime=regime, score=100, confidence=1, ml_probability=0.999, live_expectancy=50)
    baseline = risk.calculate_dynamic_risk(plain)["risk_pct"]
    assert risk.calculate_dynamic_risk(boosted)["risk_pct"] == baseline <= 0.5
    assert risk_manager.RiskManager(10_000).get_dynamic_risk_pct(boosted) == baseline


def test_only_qualified_calibration_supplies_the_primary_probability_weight():
    item = signal(ml_probability_calibrated=0.6, ml_calibration_validated=True,
                  ml_calibration_version="audit", ml_calibration_validation_rows=250,
                  ml_calibration_brier=0.16, ml_calibration_ece=0.04)
    assert risk.calculate_dynamic_risk(item)["risk_pct"] == pytest.approx(0.4)
    item["ml_calibration_brier"] = -1
    assert risk.calculate_dynamic_risk(item)["risk_pct"] == 0


def test_small_drawdown_throttles_remain_below_the_old_floor(monkeypatch):
    monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.001")
    item = signal()
    item["risk_profile"] = risk.calculate_dynamic_risk(item, account_state={"drawdown": 0.08})
    assert item["risk_profile"]["risk_pct"] == pytest.approx(0.0005)
    units = risk.calculate_position_size(item, 1)
    assert units is not None and 0 < units < 0.01 and units * 5 <= 0.0005 / 100


@pytest.mark.parametrize("source", ["explicit", "profile", "environment"])
def test_zero_risk_is_not_replaced_by_an_or_fallback(source, monkeypatch):
    item = signal()
    if source == "environment":
        monkeypatch.setenv("RISK_PER_TRADE_PCT", "0")
    if source == "profile":
        item["risk_profile"] = {"risk_pct": 0}
    assert risk.calculate_position_size(item, 10_000, risk_pct=0 if source == "explicit" else None) == 0


@pytest.mark.parametrize("field,value", [("entry", float("nan")), ("stop_loss", float("inf")),
    ("stop_loss", 101), ("stop_loss", 100), ("stop_loss", True), ("direction", "invalid")])
def test_invalid_geometry_has_no_positive_quantity(field, value):
    assert risk.calculate_position_size(signal(**{field: value}), 10_000) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1, 2])
def test_invalid_explicit_risk_is_rejected(value):
    assert risk.calculate_position_size(signal(), 10_000, risk_pct=value) is None


@pytest.mark.parametrize("overrides", [{"current_exposure_pct": 10}, {"current_exposure_pct": float("nan")},
    {"asset_class": "unknown"}, {"current_exposure_pct": True}])
def test_rejected_class_cap_never_falls_back_to_a_larger_size(overrides):
    result = risk.calculate_position_size(signal(enforce_asset_caps=True, **overrides), 10_000)
    assert result is None or result == 0


def test_tiny_asset_units_are_not_rounded_up_or_replaced_with_fallback_units():
    item = signal(entry=60_000, stop_loss=59_990, enforce_asset_caps=True)
    quantity = risk.calculate_position_size(item, 10_000)
    assert quantity is not None and 0 < quantity < 0.01
    assert quantity * 60_000 <= 10_000 * 0.02
    assert quantity * 10 <= 10_000 * 0.5 / 100


def test_fractional_asset_class_exposure_cap_and_loss_budget_are_both_preserved():
    item = signal(entry=1.73, stop_loss=1.72, enforce_asset_caps=True, current_exposure_pct=9.999)
    quantity = risk.calculate_position_size(item, 100)
    assert quantity is not None and math.isfinite(quantity)
    assert quantity * 1.73 <= 100 * (10 - 9.999) / 100
    assert quantity * (1.73 - 1.72) <= 100 * 0.5 / 100


@pytest.mark.parametrize("field", ["atr_rel", "news_sentiment", "live_expectancy"])
def test_nonfinite_advice_inputs_cannot_return_positive_risk(field):
    assert risk.calculate_dynamic_risk(signal(**{field: float("nan")}))["risk_pct"] == 0


@pytest.mark.parametrize("field,value", [("MAX_SIGNAL_VOLATILITY", "nan"), ("MAX_SIGNAL_VOLATILITY", "bad"),
    ("NEWS_VOL_ADJ", "-1"), ("NEWS_VOL_ADJ", "inf")])
def test_invalid_volatility_policy_disables_primary_advice(field, value, monkeypatch):
    monkeypatch.setenv(field, value)
    assert risk.calculate_dynamic_risk(signal())["risk_pct"] == 0
    assert risk.get_max_volatility("crypto") == 0


@pytest.mark.parametrize("direction", [True, {}, [], "sideways"])
def test_invalid_direction_data_cannot_raise_or_supply_positive_advice(direction):
    assert risk.calculate_dynamic_risk(signal(direction=direction))["risk_pct"] == 0
    assert risk_manager.RiskManager(10_000).get_dynamic_risk_pct(signal(direction=direction)) == 0


def test_invalid_hard_stop_marker_cannot_supply_quantity():
    assert risk.calculate_position_size(signal(risk_profile={"risk_pct": 0.5, "hard_stop": "unknown"}), 10_000) is None


@pytest.mark.parametrize("side,stop,targets,expected", [
    ("long", 95, [1, 110, float("inf"), True, {"price": None}], 110),
    ("short", 105, [200, 90, float("nan")], 90),
    ("long", 95, [1, 95], None), ("short", 105, [105, 200], None),
    ("long", 105, [110], None), ("short", 95, [90], None),
])
def test_best_target_does_not_invent_reward_on_the_losing_side(side, stop, targets, expected):
    assert risk.best_target_for_direction(100, stop, targets, side) == expected


@pytest.mark.parametrize("field,value", [("take_profit", [1, 95]), ("take_profit", float("inf")),
    ("stop_loss", 105), ("entry", float("nan")), ("atr_rel", float("nan")),
    ("timeframe_mult", float("inf")), ("live_expectancy", float("nan"))])
def test_primary_risk_gate_blocks_invalid_geometry_or_nonfinite_input(field, value):
    item = signal(take_profit=[110], atr_rel=0.01)
    item[field] = value
    assert not risk.risk_check(item, {"drawdown": 0})


def test_risk_freshness_budget_converts_bar_minutes_to_seconds():
    item = signal(take_profit=[110], atr_rel=0.01, timeframe_minutes=60, timeframe_mult=2,
                  created_at=now_utc_naive() - timedelta(minutes=5))
    assert risk.risk_check(item, {"drawdown": 0})
    item["created_at"] = now_utc_naive() - timedelta(hours=3)
    assert not risk.risk_check(item, {"drawdown": 0})
    item["created_at"] = now_utc_naive() + timedelta(minutes=5)
    assert not risk.risk_check(item, {"drawdown": 0})
