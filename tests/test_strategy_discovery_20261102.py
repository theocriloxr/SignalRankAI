"""Strategy discovery from long price history (2 Nov 2026)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml import strategy_discovery as sd
from strategies import discovered as dz


def _frame(close: np.ndarray, spread: float = 0.002) -> pd.DataFrame:
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    idx = pd.date_range("2020-01-01", periods=len(close), freq="h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def test_backtest_stop_first_and_costs():
    # flat, then a bar that touches both stop and target: must count as a loss
    close = np.full(300, 100.0)
    df = _frame(close, spread=0.0)
    ind = dz.indicator_frame(df)
    ind["atr"] = 1.0
    ind.loc[ind.index[201], ["high", "low"]] = [103.0, 98.0]
    mask = pd.Series(False, index=ind.index)
    mask.iloc[199] = True  # signal bar 199 -> entry at open of 200
    bars, r = sd.backtest(ind, mask, "long", 1.0, 2.0, 10, cost=0.0)
    assert list(bars) == [199] and r[0] == -1.0
    bars, r = sd.backtest(ind, mask, "long", 1.0, 2.0, 10, cost=0.001)
    assert r[0] == pytest.approx(-1.0 - 0.001 * 100 / 1.0)


def test_backtest_target_and_time_exit_and_no_overlap():
    close = np.full(300, 100.0)
    df = _frame(close, spread=0.0)
    ind = dz.indicator_frame(df)
    ind["atr"] = 1.0
    ind.loc[ind.index[203], "high"] = 102.5
    mask = pd.Series(False, index=ind.index)
    mask.iloc[[199, 200, 250]] = True
    bars, r = sd.backtest(ind, mask, "long", 1.0, 2.0, 10, cost=0.0)
    # 200 overlaps the open trade from 199; 250 times out flat
    assert list(bars) == [199, 250]
    assert r[0] == pytest.approx(2.0) and r[1] == pytest.approx(0.0)


def test_metrics():
    m = sd.metrics(np.array([2.0, -1.0, 2.0, -1.0]))
    assert m["trades"] == 4 and m["win_rate"] == 0.5 and m["expectancy_r"] == 0.5 and m["profit_factor"] == 2.0


def test_random_walk_produces_no_survivors():
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 6000)))
    result = sd.research_frame("TESTUSDT", "crypto", "1h", _frame(close), sd.Rules())
    assert result["configs"] == sum(len(g) for g in dz.FAMILY_GRID.values()) * 2 * len(dz.EXIT_GRID)
    assert result["survivors"] == []


def test_persistent_edge_is_found_and_validated_out_of_sample():
    # Strong drift with pullbacks: trend-following longs should survive all three windows.
    rng = np.random.default_rng(11)
    steps = rng.normal(0.0012, 0.004, 6000)
    close = 100 * np.exp(np.cumsum(steps))
    result = sd.research_frame("TESTUSDT", "crypto", "1h", _frame(close), sd.Rules())
    assert result["survivors"], result
    best = result["survivors"][0]
    assert best["direction"] == "long"
    assert best["metrics"]["validation"]["expectancy_r"] > 0 and best["metrics"]["holdout"]["expectancy_r"] > 0
    assert best["spec_id"].startswith("ds_")


def test_lifecycle_new_shadow_decay_and_reinstate(monkeypatch):
    monkeypatch.setattr(sd, "_forward_verdict", lambda spec: None)
    spec = {"spec_id": "ds_a", "asset": "BTCUSDT", "timeframe": "1h", "family": "donchian_breakout"}
    merged = sd.merge_specs([], [spec], {})
    assert merged[0]["state"] == "shadow"
    decayed = sd.merge_specs(merged, [], {"ds_a": {"trades": 12, "expectancy_r": -0.3}})
    assert decayed[0]["state"] == "retired" and decayed[0]["retired_reason"] == "decayed_recent_backtest"
    back = sd.merge_specs(decayed, [spec], {})
    assert back[0]["state"] == "shadow"


def test_forward_record_approves_or_retires(monkeypatch):
    spec = {"spec_id": "ds_b", "asset": "EURUSD", "timeframe": "4h", "family": "rsi_reversal"}
    monkeypatch.setattr(sd, "_forward_verdict", lambda s: "approved")
    assert sd.merge_specs([], [spec], {})[0]["state"] == "approved"
    monkeypatch.setattr(sd, "_forward_verdict", lambda s: "retired")
    assert sd.merge_specs([], [spec], {})[0]["state"] == "retired"


def _spec_matching_last_bar(ind):
    return {"spec_id": "ds_test000001", "asset": "BTCUSDT", "timeframe": "1d", "family": "atr_momentum",
            "params": {"n": 10, "k": 0.0, "trend": 0}, "direction": "long", "stop_atr": 1.5, "target_r": 2.0,
            "metrics": {"oos": {"trades": 40, "expectancy_r": 0.3}}, "state": "shadow"}


def test_engine_hook_shadow_records_and_live_returns(monkeypatch):
    close = 100 * np.exp(np.cumsum(np.full(220, 0.002)))
    df = _frame(close)
    candles = [{"open": o, "high": h, "low": lo, "close": c} for o, h, lo, c in df.to_numpy()]
    spec = _spec_matching_last_bar(df)
    recorded = []
    monkeypatch.setattr(dz, "load_specs", lambda: [spec])
    monkeypatch.setattr(dz, "_record_shadow", lambda cand, s: recorded.append(cand))
    dz._seen.clear()
    monkeypatch.setenv("DISCOVERED_STRATEGIES_MODE", "shadow")
    assert dz.discovered_candidates("BTCUSDT", "24h", {"candles": candles}) == []
    assert len(recorded) == 1 and recorded[0]["direction"] == "LONG"
    cand = recorded[0]
    assert cand["stop"] < cand["entry"] < cand["take_profit"]
    assert (cand["take_profit"] - cand["entry"]) == pytest.approx(2.0 * (cand["entry"] - cand["stop"]))
    # same bar is never recorded twice
    dz.discovered_candidates("BTCUSDT", "24h", {"candles": candles})
    assert len(recorded) == 1
    # live mode only returns approved specs
    dz._seen.clear()
    monkeypatch.setenv("DISCOVERED_STRATEGIES_MODE", "live")
    assert dz.discovered_candidates("BTCUSDT", "24h", {"candles": candles}) == []
    spec["state"] = "approved"
    dz._seen.clear()
    out = dz.discovered_candidates("BTCUSDT", "24h", {"candles": candles})
    assert len(out) == 1 and out[0]["strategy_group"] == "discovered"


def test_engine_hook_off_and_short_history(monkeypatch):
    monkeypatch.setattr(dz, "load_specs", lambda: [_spec_matching_last_bar(None)])
    monkeypatch.setenv("DISCOVERED_STRATEGIES_MODE", "off")
    assert dz.discovered_candidates("BTCUSDT", "1d", {"candles": []}) == []
    monkeypatch.setenv("DISCOVERED_STRATEGIES_MODE", "shadow")
    assert dz.discovered_candidates("BTCUSDT", "1d", {"candles": [{"open": 1, "high": 1, "low": 1, "close": 1}]}) == []


def test_symbol_mapping():
    assert sd.yahoo_symbol("EURUSD", "forex") == "EURUSD=X"
    assert sd.yahoo_symbol("US500", "indices") == "^GSPC"
    assert sd.yahoo_symbol("XAUUSD", "commodities") == "GC=F"
    assert sd.yahoo_symbol("BRK.B", "stocks") == "BRK-B"


def test_every_family_evaluates_both_directions():
    rng = np.random.default_rng(3)
    ind = dz.indicator_frame(_frame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))))
    for family, grid in dz.FAMILY_GRID.items():
        for direction in ("long", "short"):
            mask = dz.entry_mask(ind, family, grid[0], direction)
            assert mask.dtype == bool and len(mask) == len(ind)
