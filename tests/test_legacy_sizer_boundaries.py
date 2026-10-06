"""Both legacy import paths use one bounded policy and isolated account state."""
import json
import pytest

from engine.risk_sizer import SmartRiskSizer, get_risk_sizer
from engine import risk_manager
from core.tier_constants import DD_HARD_LIMIT


def qualified(probability):
    return {"direction": "long", "ml_probability_calibrated": probability,
            "ml_calibration_validated": True, "ml_calibration_version": "audit",
            "ml_calibration_validation_rows": 250, "ml_calibration_brier": 0.16, "ml_calibration_ece": 0.04}


def test_legacy_imports_share_the_same_implementation():
    assert risk_manager.SmartRiskSizer is SmartRiskSizer


def test_missing_model_does_not_crash_logging_or_invent_a_probability():
    sizer = SmartRiskSizer()
    assert sizer.calculate_position_size(100, 50) == 2
    for probability in [0, 0.7, 0.99, float("nan"), True]:
        assert sizer.calculate_position_size(100, 50, probability) == 2
    assert sizer.calculate_position_size(100, 50, ml_prob=0.99) == 2


def test_qualified_threshold_weights_reduce_but_cannot_raise_the_base():
    sizer = SmartRiskSizer()
    assert sizer.calculate_position_size(100, 50, signal=qualified(0.9)) == 2
    assert sizer.calculate_position_size(100, 50, signal=qualified(0.7)) == 1
    damaged = qualified(0.9)
    damaged["ml_calibration_brier"] = -1
    assert sizer.calculate_position_size(100, 50, signal=damaged) == 0
    assert sizer.get_risk_config()["high_risk_pct"] <= 0.01


@pytest.mark.parametrize("equity,base", [(float("nan"), 0.01), (True, 0.01), (-1, 0.01),
    (10000, 0), (10000, float("inf")), (10000, True), (10000, -0.01), (10000, 1)])
def test_invalid_or_disabled_budgets_cannot_return_positive_units(equity, base):
    assert SmartRiskSizer(equity, base).calculate_position_size(100, 50) == 0


def test_zero_small_risk_and_account_stops_cannot_be_revived_by_floors():
    sizer = SmartRiskSizer(1, 0.000001)
    units = sizer.calculate_position_size(100, 50)
    assert 0 < units < 0.01 and units * 50 <= 0.000001
    assert sizer.calculate_position_size(100, 50, account_state={"drawdown": DD_HARD_LIMIT}) == 0
    assert sizer.calculate_position_size(100, 50, account_state={"drawdown": float("nan")}) == 0


@pytest.mark.parametrize("entry,stop", [(100, 105), (100, 100), (float("nan"), 95), (100, True)])
def test_invalid_directional_geometry_is_rejected(entry, stop):
    assert SmartRiskSizer().calculate_position_size(entry, stop, signal=qualified(0.9)) == 0


def test_expensive_asset_quote_limit_is_converted_to_units():
    units = SmartRiskSizer().calculate_position_size(60000, 59990)
    assert units * 60000 <= 1000 and units * 10 <= 100


def test_convenience_calls_cannot_inherit_another_accounts_equity_or_risk():
    first = get_risk_sizer(100000, 0.005)
    second = get_risk_sizer(5000, 0.001)
    default = get_risk_sizer()
    assert first is not second and second is not default
    assert (first.account_balance, first.base_risk_pct) == (100000, 0.005)
    assert (second.account_balance, second.base_risk_pct) == (5000, 0.001)
    assert (default.account_balance, default.base_risk_pct) == (10000, 0.01)
    second.update_account_balance(100)
    assert first.account_balance == 100000 and default.account_balance == 10000


@pytest.mark.parametrize("field,value", [("high_confidence_threshold", 0.5), ("high_risk_multiplier", float("nan")),
    ("medium_risk_multiplier", -1), ("base_risk_pct", float("inf")), ("account_balance", True)])
def test_invalid_configuration_cannot_supply_units_or_advertise_positive_risk(field, value):
    sizer = SmartRiskSizer()
    setattr(sizer, field, value)
    assert sizer.calculate_position_size(100, 50, signal=qualified(0.9)) == 0
    config = sizer.get_risk_config()
    json.dumps(config, allow_nan=False)
    assert not config["configuration_valid"]
    assert config["high_risk_pct"] == config["medium_risk_pct"] == config["low_risk_pct"] == 0
