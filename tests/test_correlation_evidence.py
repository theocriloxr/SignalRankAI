"""Admission must not mistake invalid or unaligned data for diversification."""
from copy import deepcopy

import numpy as np
import pytest

from engine import risk
from engine.risk_manager import CorrelationManager


def candles(returns, *, offset=0, milliseconds=False):
    prices = 100 * np.cumprod(np.r_[1.0, 1.0 + np.asarray(returns)])
    return [{"timestamp": (1_780_000_000 + offset + i * 3600) * (1000 if milliseconds else 1),
             "close": float(price)} for i, price in enumerate(prices)]


@pytest.fixture
def histories():
    index = np.arange(40)
    return {"BTC": candles(0.01 + 0.002 * np.sin(index)),
            "ETH": candles(0.01 + 0.002 * np.cos(index * 2))}


def test_price_trends_do_not_substitute_for_return_correlation(histories):
    assert np.corrcoef([c["close"] for c in histories["BTC"]],
                      [c["close"] for c in histories["ETH"]])[0, 1] > 0.99
    assert risk.check_correlation_gate(" btc ", ["eth"], histories) == (True, "ok")


@pytest.mark.parametrize("sign", [1, -1])
def test_both_positive_and_negative_return_concentration_block(sign):
    changes = 0.01 * np.sin(np.arange(30))
    histories = {"BTC": candles(changes), "ETH": candles(sign * changes, milliseconds=True)}
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories)[0]


@pytest.mark.parametrize("threshold", [True, None, 0, -1, 1.1, float("nan"), float("inf")])
def test_invalid_threshold_cannot_disable_the_gate(histories, threshold):
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories, threshold)[0]


@pytest.mark.parametrize("bad", [None, [], [1.0] * 40, [{"close": 1}] * 40,
                                 [{"close": 1, "timestamp": []}] * 40])
def test_absent_or_untimestamped_history_blocks(histories, bad):
    histories["ETH"] = bad
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories)[0]


@pytest.mark.parametrize("field,value", [("close", float("nan")), ("close", 0),
    ("close", True), ("timestamp", None), ("timestamp", "invalid"), ("timestamp", True)])
def test_invalid_rows_are_not_silently_dropped(histories, field, value):
    histories["ETH"][15][field] = value
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories)[0]


def test_equal_length_but_different_intervals_do_not_align(histories):
    for row in histories["ETH"]:
        row["timestamp"] += 1800
    assert risk.check_correlation_gate("BTC", ["ETH"], histories) == (False, "insufficient_aligned_returns")


def test_shared_endpoints_cannot_match_different_return_start_times(histories):
    histories["ETH"] = histories["ETH"][::2]
    assert risk.check_correlation_gate("BTC", ["ETH"], histories) == (False, "insufficient_aligned_returns")


@pytest.mark.parametrize("mutation", ["constant", "duplicate", "reversed", "short"])
def test_undefined_or_invalid_series_blocks(histories, mutation):
    rows = histories["ETH"]
    if mutation == "constant":
        for row in rows:
            row["close"] = 100
    elif mutation == "duplicate":
        rows[4]["timestamp"] = rows[3]["timestamp"]
    elif mutation == "reversed":
        rows.reverse()
    else:
        histories["ETH"] = rows[:10]
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories)[0]


def test_existing_symbol_and_ambiguous_evidence_block(histories):
    assert not risk.check_correlation_gate("BTC", ["btc"], histories)[0]
    histories[" eth "] = deepcopy(histories["ETH"])
    assert not risk.check_correlation_gate("BTC", ["ETH"], histories)[0]
    assert not risk.check_correlation_gate("BTC", "ETH", histories)[0]
    assert risk.check_correlation_gate("BTC", [], None)[0]


def primary_signal(**extra):
    return {"asset": "BTC", "asset_class": "crypto", "direction": "long", "entry": 100,
            "stop_loss": 95, "take_profit": [110], "atr_rel": 0.01,
            "active_positions": ["ETH"], **extra}


@pytest.mark.parametrize("active", [None, [], {"one": None}, {"one": {}}, {"one": {"symbol": True}}])
def test_unknown_exposure_cannot_become_an_empty_portfolio(active):
    with pytest.raises(ValueError):
        risk.correlation_positions(active)
    assert not risk.risk_check(primary_signal(active_positions=None), {"drawdown": 0})


def test_valid_exposure_is_normalized_and_deduplicated():
    assert risk.correlation_positions({}) == []
    assert risk.correlation_positions({"one": {"symbol": " eth "}, "two": {"asset": "ETH"}}) == ["ETH"]


def test_primary_fetch_keeps_timestamps_and_blocks_unavailable_evidence(monkeypatch, histories):
    monkeypatch.setenv("ENABLE_CORRELATION_GATE", "true")
    async def fetch(symbol, timeframes):
        return {timeframes[0]: {"candles": histories[symbol]}}
    monkeypatch.setattr("data.market_data.fetch_market_data_cached", fetch)
    assert risk.risk_check(primary_signal(), {"drawdown": 0})
    histories["ETH"] = []
    assert not risk.risk_check(primary_signal(), {"drawdown": 0})
    assert not risk.risk_check(primary_signal(active_positions="ETH"), {"drawdown": 0})
    monkeypatch.setenv("MAX_PORTFOLIO_CORRELATION", "invalid")
    assert not risk.risk_check(primary_signal(correlation_prices=histories), {"drawdown": 0})


def test_optional_controller_uses_coroutines_and_blocks_provider_errors(monkeypatch, histories):
    from engine.signal_controller import SignalController
    monkeypatch.setenv("ENABLE_CORRELATION_CHECK", "true")
    monkeypatch.setattr("core.redis_state.state.get_active_trades_sync", lambda **kw: {"one": {"symbol": "ETH"}})
    calls = []
    async def fetch(symbol, timeframes):
        calls.append(symbol)
        return {timeframes[0]: {"candles": histories[symbol]}}
    monkeypatch.setattr("data.market_data.fetch_market_data_cached", fetch)
    controller = SignalController()
    assert controller.can_emit(primary_signal(timeframe="1h"))
    assert sorted(calls) == ["BTC", "ETH"]
    async def unavailable(*args):
        raise TimeoutError("synthetic outage")
    monkeypatch.setattr("data.market_data.fetch_market_data_cached", unavailable)
    assert not controller.can_emit(primary_signal(timeframe="1h"))
    monkeypatch.setattr("core.redis_state.state.get_active_trades_sync", lambda **kw: None)
    assert not controller.can_emit(primary_signal(timeframe="1h"))


def test_legacy_manager_rejects_missing_nonfinite_and_misaligned_returns():
    manager = CorrelationManager()
    returns = np.sin(np.arange(30))
    assert not manager.can_add_correlated_position("BTC", ["ETH"])[0]
    for bad in (np.array([float("nan")] * 30), returns[:-1], np.ones(30)):
        assert not manager.can_add_correlated_position("BTC", ["ETH"], returns_data={"BTC": returns, "ETH": bad})[0]
    assert not manager.can_add_correlated_position("BTC", ["ETH"], returns_data={"BTC": returns, "ETH": returns})[0]


@pytest.mark.parametrize("snapshot", [None, [], {"one": "broken json"}, {"one": "null"},
                                     {"valid": '{"symbol":"ETH"}', "broken": "[]"}])
def test_strict_shared_snapshot_cannot_hide_corrupt_records(monkeypatch, snapshot):
    from core.redis_state import RedisState
    from unittest.mock import Mock
    state = RedisState()
    monkeypatch.setattr(state, "_get_redis_sync", lambda: Mock(hgetall=lambda key: snapshot))
    with pytest.raises(RuntimeError, match="active_trade_snapshot_unavailable"):
        state.get_active_trades_sync(require_complete=True)


def test_strict_shared_snapshot_distinguishes_empty_from_outage(monkeypatch):
    from core.redis_state import RedisState
    from unittest.mock import Mock
    state = RedisState()
    monkeypatch.setattr(state, "_get_redis_sync", lambda: None)
    assert state.get_active_trades_sync() == {}
    with pytest.raises(RuntimeError):
        state.get_active_trades_sync(require_complete=True)
    client = Mock()
    monkeypatch.setattr(state, "_get_redis_sync", lambda: client)
    client.hgetall.return_value = {}
    assert state.get_active_trades_sync(require_complete=True) == {}
    client.hgetall.side_effect = TimeoutError("private connection detail")
    with pytest.raises(RuntimeError, match="^active_trade_snapshot_unavailable$"):
        state.get_active_trades_sync(require_complete=True)
