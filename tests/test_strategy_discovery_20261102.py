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
    price_only = sum(len(g) for f, g in dz.FAMILY_GRID.items() if f not in dz.VOLUME_FAMILIES)
    assert result["configs"] == price_only * 2 * len(dz.STYLES["swing"]["exits"])  # no volume in this frame
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
    spec = {"spec_id": "ds_a", "asset": "BTCUSDT", "timeframe": "1h", "family": "donchian_breakout",
            "trade_profile": "day"}
    merged = sd.merge_specs([], [spec], {})
    assert merged[0]["state"] == "shadow"
    decayed = sd.merge_specs(merged, [], {"ds_a": {"trades": 12, "expectancy_r": -0.3}})
    assert decayed[0]["state"] == "retired" and decayed[0]["retired_reason"] == "decayed_recent_backtest"
    back = sd.merge_specs(decayed, [spec], {})
    assert back[0]["state"] == "shadow"


def test_forward_record_approves_or_retires(monkeypatch):
    spec = {"spec_id": "ds_b", "asset": "EURUSD", "timeframe": "4h", "family": "rsi_reversal",
            "trade_profile": "swing"}
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


def test_schedule_follows_last_published_run(monkeypatch):
    import time as _t

    built = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(_t.time() - 3600))
    monkeypatch.setattr(sd, "_load_published", lambda: {"summary": {"built_at": built}})
    assert 7 * 86400 - 3700 < sd.seconds_until_due(7 * 86400) <= 7 * 86400 - 3500
    monkeypatch.setattr(sd, "_load_published", lambda: {})
    assert sd.seconds_until_due(7 * 86400) == 0.0


def test_survivors_carry_their_trading_style():
    rng = np.random.default_rng(11)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0012, 0.004, 6000)))
    result = sd.research_frame("TESTUSDT", "crypto", "1h", _frame(close), sd.Rules(), style="flip")
    assert result["survivors"]
    for spec in result["survivors"]:
        assert spec["trade_profile"] == "flip" and spec["target_r"] >= 3.0
        assert spec["max_hold_bars"] == dz.STYLES["flip"]["hold"]["1h"]


def test_styles_cover_every_engine_timeframe():
    assert sd.styles_for("5m") == ["scalp"]
    assert set(sd.styles_for("15m")) == {"scalp", "day", "flip"}
    assert set(sd.styles_for("1d")) == {"swing", "position"}
    for tf in sd.RESEARCH_TIMEFRAMES:
        assert sd.styles_for(tf)


def test_volume_families_need_real_volume():
    rng = np.random.default_rng(5)
    df = _frame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800))))
    no_volume = dz.indicator_frame(df)
    assert not dz.has_volume(no_volume)
    assert not dz.entry_mask(no_volume, "volume_breakout", {"n": 20, "vz": 2.0}, "long").any()
    df["volume"] = rng.uniform(100, 200, len(df))
    df.iloc[400, df.columns.get_loc("volume")] = 5000.0
    df.iloc[400, df.columns.get_loc("close")] = df["high"].iloc[350:400].max() * 1.05
    with_volume = dz.indicator_frame(df)
    assert dz.has_volume(with_volume)
    assert dz.entry_mask(with_volume, "volume_breakout", {"n": 20, "vz": 2.0}, "long").iloc[400]


def test_engine_candles_keep_volume():
    candles = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}] * 210
    frame = dz._frame_from_candles(candles)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"] and frame["volume"].iloc[0] == 10
    rows = [[0, 1, 2, 0.5, 1.5]] * 210  # no volume column
    assert dz._frame_from_candles(rows)["volume"].iloc[0] == 0.0


def test_unstyled_first_generation_specs_are_superseded(monkeypatch):
    monkeypatch.setattr(sd, "_forward_verdict", lambda spec: None)
    old = {"spec_id": "ds_old", "asset": "BTCUSDT", "timeframe": "4h", "family": "x", "state": "shadow"}
    merged = sd.merge_specs([old], [], {})
    assert merged[0]["state"] == "retired" and merged[0]["retired_reason"] == "superseded_by_style_research"


def test_flip_profile_matching():
    from services.trade_profiles import normalize_trade_profile, signal_matches_user_profile

    assert normalize_trade_profile("flipper") == "flip"
    three_r = {"timeframe": "1h", "direction": "LONG", "entry": 100.0, "stop_loss": 99.0, "take_profit": [103.5]}
    two_r = dict(three_r, take_profit=[102.0])
    assert signal_matches_user_profile(three_r, "flip")
    assert not signal_matches_user_profile(two_r, "flip")
    assert not signal_matches_user_profile(dict(three_r, timeframe="1d"), "flip")
    assert signal_matches_user_profile({"trade_profile": "flip", "timeframe": "1d"}, "flip")
    # explicit styles from discovered specs are honoured for other profiles too
    assert signal_matches_user_profile({"trade_profile": "scalp", "timeframe": "15m"}, "scalp")
