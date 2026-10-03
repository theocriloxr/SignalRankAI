import pytest

from core.partial_exit_accounting import calculate_partial_exit_result


def result(**changes):
    values = dict(entry=100, stop_loss=95, take_profit=[110, 120, 130],
                  direction="BUY", highest_tp=1, residual_exit_r=0)
    values.update(changes)
    return calculate_partial_exit_result(**values)


@pytest.mark.parametrize("changes", [
    {"direction": "unknown"}, {"direction": None},
    {"stop_loss": 105}, {"stop_loss": -5},
    {"take_profit": [90]}, {"take_profit": [120, 110], "highest_tp": 2},
    {"take_profit": [110, 110], "highest_tp": 2},
    {"highest_tp": 3}, {"highest_tp": "bad"},
    {"residual_exit_r": float("nan")}, {"residual_exit_r": float("inf")},
])
def test_invalid_partial_exit_inputs_cannot_manufacture_performance(changes):
    assert result(**changes) is None


def test_residual_loss_reduces_both_r_and_percentage():
    outcome = result(residual_exit_r=-1)
    assert outcome.realized_r == 0.5
    assert outcome.realized_percent == 2.5
    assert outcome.accounting_basis == "planned_signal_exits"


def test_short_residual_math_preserves_signed_accounting():
    outcome = result(direction="SELL", stop_loss=105, take_profit=[90, 80],
                     highest_tp=2, residual_exit_r=-1)
    assert outcome.realized_r == 1.75
    assert outcome.realized_percent == 8.75
