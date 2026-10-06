"""Legacy spot advice cannot bypass a loss budget or account drawdown stop."""
from types import SimpleNamespace

import pytest

from engine import risk_manager
from engine.signal_metrics import resolve_calibrated_probability


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(risk_manager, "BASE_RISK_PCT", 0.5)
    monkeypatch.setenv("ML_RISK_BASE", "0.5")
    monkeypatch.setenv("ML_RISK_RANGE", "0.5")
    return risk_manager.RiskManager(10_000)


def signal(**overrides):
    return {"entry": 100.0, "stop_loss": 95.0, "direction": "long", **overrides}


def test_missing_model_and_heuristic_scores_cannot_raise_the_risk_budget(manager):
    baseline = manager.get_dynamic_risk_pct(signal())
    for score in [0, 70, 100]:
        assert manager.get_dynamic_risk_pct(signal(score=score, confidence=1, ml_probability=0.999)) == baseline
    assert manager.get_dynamic_risk_pct(signal(regime="trending", news_sentiment=1.5, live_expectancy=50)) <= 0.5


@pytest.mark.parametrize("state", [SimpleNamespace(drawdown=0.15), {"drawdown": 0.15}])
def test_account_hard_stop_reaches_sizing_and_cannot_be_revived_by_a_minimum_size(manager, state):
    assert manager.calculate_position_size(signal(), 10_000, account_state=state) == 0


def test_soft_drawdown_throttle_is_not_erased_by_a_minimum_risk_floor(manager):
    base = manager.get_dynamic_risk_pct(signal(live_expectancy=0))
    throttled = manager.get_dynamic_risk_pct(signal(live_expectancy=0), SimpleNamespace(drawdown=0.08))
    assert throttled == base / 2 and 0 < throttled < 0.25


@pytest.mark.parametrize("entry,stop,equity", [
    (float("nan"), 95, 10_000), (100, float("inf"), 10_000), (100, 95, float("nan")),
    (100, 95, 0), (100, 95, -1), (100, 95, True), (True, 0.5, 10_000),
    (100, 101, 10_000), (100, 100, 10_000), (0, 95, 10_000),
])
def test_invalid_geometry_and_equity_cannot_produce_positive_units(manager, entry, stop, equity):
    assert manager.calculate_position_size(signal(entry=entry, stop_loss=stop), equity) == 0


@pytest.mark.parametrize("drawdown", [float("nan"), float("inf"), -0.1, True, None])
def test_invalid_account_drawdown_cannot_produce_risk_advice(manager, drawdown):
    assert manager.get_dynamic_risk_pct(signal(), SimpleNamespace(drawdown=drawdown)) == 0


@pytest.mark.parametrize("field", ["news_sentiment", "live_expectancy"])
def test_nonfinite_heuristics_are_rejected_instead_of_clamped_to_positive_risk(manager, field):
    assert manager.get_dynamic_risk_pct(signal(**{field: float("nan")})) == 0


@pytest.mark.parametrize("name,value", [("ML_RISK_BASE", "nan"), ("ML_RISK_RANGE", "inf"),
                                        ("ML_RISK_RANGE", "1"), ("ML_RISK_BASE", "bad")])
def test_invalid_risk_weight_configuration_fails_closed(manager, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert manager.get_dynamic_risk_pct(signal()) == 0


def test_small_positive_advice_does_not_round_up_past_the_loss_budget(manager, monkeypatch):
    monkeypatch.setattr(risk_manager, "BASE_RISK_PCT", 0.001)
    quantity = manager.calculate_position_size(signal(), 1.0)
    assert 0 < quantity < 0.01
    assert quantity * 5 <= 1.0 * 0.001 / 100


def test_notional_cap_is_converted_to_units_for_expensive_assets(manager):
    quantity = manager.calculate_position_size(signal(entry=60_000, stop_loss=59_990), 10_000)
    assert quantity * 60_000 <= 10_000 * 0.1
    assert quantity * 10 <= 10_000 * 0.5 / 100


@pytest.mark.parametrize("base", [0, -0.1, float("nan"), float("inf"), True])
def test_disabled_or_invalid_base_risk_cannot_be_revived_by_minimum_floors(manager, monkeypatch, base):
    monkeypatch.setattr(risk_manager, "BASE_RISK_PCT", base)
    assert manager.calculate_position_size(signal(), 10_000) == 0


def test_short_stop_geometry_is_checked_before_sizing(manager):
    assert manager.calculate_position_size(signal(direction="short", stop_loss=95), 10_000) == 0
    assert manager.calculate_position_size(signal(direction="short", stop_loss=105), 10_000) > 0


def test_only_qualified_model_evidence_can_supply_the_probability_weight(manager):
    qualified = signal(ml_probability=0.999, ml_probability_calibrated=0.6,
        ml_calibration_version="calibration-audit", ml_calibration_validated=True,
        ml_calibration_validation_rows=250, ml_calibration_brier=0.16, ml_calibration_ece=0.04)
    assert resolve_calibrated_probability(qualified) == 0.6
    assert manager.get_dynamic_risk_pct(qualified) == pytest.approx(0.4)
    qualified["ml_calibration_brier"] = -1
    assert resolve_calibrated_probability(qualified) is None
    assert manager.get_dynamic_risk_pct(qualified) == 0
