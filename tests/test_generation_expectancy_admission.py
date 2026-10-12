"""The generation gate consumes qualification evidence before deciding risk."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.core import _risk_check_with_history
from engine.risk import risk_check, risk_check_with_reason


@pytest.fixture
def candidate(monkeypatch):
    monkeypatch.setenv("EXPECTANCY_HARD_BLOCK_ENABLED", "1")
    monkeypatch.setenv("HISTORICAL_PERFORMANCE_CONTEXT_ENABLED", "1")
    monkeypatch.setenv("ENABLE_CORRELATION_GATE", "1")
    monkeypatch.setenv("MIN_RR_RISK", "1.5")
    monkeypatch.setenv("MAX_SIGNAL_VOLATILITY", "0.12")
    monkeypatch.setenv("NEWS_VOL_ADJ", "0.1")
    return {"asset": "BTCUSDT", "strategy_name": "EMA Trend", "timeframe": "5m",
            "direction": "LONG", "entry": 100., "stop_loss": 98., "take_profit": [104.],
            "volatility": 0.01, "active_positions": []}


def history_provider(monkeypatch, context=None, error=None):
    provider = AsyncMock(return_value=context, side_effect=error)
    monkeypatch.setattr("engine.expectancy_gate.get_best_live_performance_context", provider)
    return provider


def test_qualified_history_can_reach_the_same_configured_risk_gate(candidate, monkeypatch):
    provider = history_provider(monkeypatch, {"actionable": True, "sample_size": 40,
        "expectancy_r": .42, "scope": "asset_strategy_timeframe", "fallback_depth": 0})
    account = SimpleNamespace(drawdown=0.)
    assert risk_check(candidate, account) is False  # Reproduces the former ordering failure.
    assert _risk_check_with_history(candidate, account, "BTCUSDT") is True
    assert candidate["live_expectancy"] == .42
    assert candidate["historical_sample_size"] == 40
    assert candidate["risk_rejection_reason"] == "ok"
    assert provider.await_args.kwargs["strategy"] == "EMA Trend"
    assert provider.await_args.kwargs["timeframe"] == "5m"


@pytest.mark.parametrize("context,reason", [
    ({"actionable": False, "expectancy_r": .9, "sample_size": 2}, "expectancy_unavailable"),
    ({"actionable": True, "expectancy_r": -.3, "sample_size": 40}, "expectancy_below_minimum"),
    ({"actionable": True, "expectancy_r": .1, "sample_size": 40}, "expectancy_below_minimum"),
    (None, "expectancy_unavailable"),
])
def test_unqualified_history_cannot_borrow_strategy_supplied_expectancy(candidate, monkeypatch, context, reason):
    history_provider(monkeypatch, context)
    candidate["live_expectancy"] = 99.
    assert _risk_check_with_history(candidate, SimpleNamespace(drawdown=0.), "BTCUSDT") is False
    assert candidate["risk_rejection_reason"] == reason


def test_history_read_failure_remains_closed(candidate, monkeypatch):
    history_provider(monkeypatch, error=TimeoutError("unavailable"))
    candidate["live_expectancy"] = 99.
    assert _risk_check_with_history(candidate, SimpleNamespace(drawdown=0.), "BTCUSDT") is False
    assert candidate["risk_rejection_reason"] == "expectancy_unavailable"
    assert candidate["historical_evidence_actionable"] is False


def test_disabling_history_does_not_disable_the_hard_gate(candidate, monkeypatch):
    provider = history_provider(monkeypatch, {"actionable": True, "expectancy_r": .9})
    monkeypatch.setenv("HISTORICAL_PERFORMANCE_CONTEXT_ENABLED", "0")
    candidate["live_expectancy"] = 99.
    assert _risk_check_with_history(candidate, SimpleNamespace(drawdown=0.), "BTCUSDT") is False
    provider.assert_not_awaited()


@pytest.mark.parametrize("patch,drawdown,reason", [
    ({"volatility": .5}, 0., "volatility"),
    ({"take_profit": [100.5]}, 0., "minimum_rr"),
    ({"active_positions": None}, 0., "active_positions_unavailable"),
    ({"active_positions": ["BTCUSDT"]}, 0., "correlation:existing_symbol_exposure"),
    ({}, 1., "account_drawdown"),
])
def test_qualified_history_cannot_override_other_risk_vetoes(candidate, monkeypatch, patch, drawdown, reason):
    history_provider(monkeypatch, {"actionable": True, "expectancy_r": .42, "sample_size": 40})
    candidate.update(patch)
    account = SimpleNamespace(drawdown=drawdown)
    assert _risk_check_with_history(candidate, account, "BTCUSDT") is False
    assert candidate["risk_rejection_reason"] == reason
    assert risk_check_with_reason(candidate, account) == (False, reason)
    assert risk_check(candidate, account) is False
