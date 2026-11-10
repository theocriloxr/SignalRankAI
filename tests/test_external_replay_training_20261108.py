"""More training data from long public history (owner request, 8 Nov 2026)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml import external_replay as er


def _walk(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.008, n)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": rng.uniform(100, 200, n)},
                        index=idx)


def test_labels_have_no_lookahead_on_a_random_walk():
    df = _walk()
    rows = er.replay_frame("BTCUSDT", "crypto", "1h", df, {"1h": df}, before=None, max_rows=100_000)
    win = float(np.mean([r["target"] for r in rows]))
    # A 1.5R target against a 1R stop wins 40% of the time on a driftless walk.
    assert len(rows) > 1000 and abs(win - 0.40) < 0.04


def test_rows_stay_older_than_the_bots_evidence_and_families_are_balanced():
    df = _walk()
    cutoff = pd.Timestamp("2024-06-01", tz="UTC")
    rows = er.replay_frame("BTCUSDT", "crypto", "1h", df, {"1h": df}, before=cutoff, max_rows=400)
    assert len(rows) == 400 and max(r["created_at"] for r in rows) < cutoff.tz_convert(None).to_pydatetime()
    counts = pd.Series([r["strategy_name"] for r in rows]).value_counts()
    assert counts.max() <= counts.min() + 400 // len(counts) + 1 or len(counts) == 1
    assert all(r["source_type"] == "external_replay" and r["sample_weight"] == 0.25 for r in rows)


def test_augment_caps_rows_and_marks_them_fit_only(monkeypatch):
    internal = pd.DataFrame({"asset": ["BTCUSDT"] * 30, "timeframe": ["1h"] * 30, "source_type": ["live_delivery"] * 30,
                             "created_at": pd.date_range("2026-08-01", periods=30, freq="D"), "target": [1, 0] * 15})
    captured = {}

    def fake_build(pairs, *, before, budget_rows, client=None, deadline=None):
        captured.update(before=before, budget=budget_rows, pairs=pairs)
        return [{"asset": "BTCUSDT", "timeframe": "1h", "source_type": "external_replay", "target": 1,
                 "created_at": pd.Timestamp("2025-01-01").to_pydatetime(), "strategy_name": "replay_x"}] * budget_rows, {}

    monkeypatch.setattr(er, "build_rows", fake_build)
    monkeypatch.setenv("ML_EXTERNAL_REPLAY_MAX_RATIO", "9")  # clamped to 2.0
    out, evidence = er.augment(internal)
    assert captured["budget"] == 60 and evidence["rows"] <= 60 and evidence["applied"]
    # 10 Nov 2026: replay stops one day before the calibration/validation windows (70 % of the bot's rows),
    # no longer before the oldest row; fit-only rows never reach validation either way.
    assert captured["before"] == pd.Timestamp("2026-08-20", tz="UTC")
    monkeypatch.setenv("ML_EXTERNAL_REPLAY_ENABLED", "false")
    assert er.augment(internal)[0] is internal


def test_fit_only_rows_never_reach_validation():
    from ml.train_model import train_model

    rng = np.random.default_rng(1)
    n_int, n_ext = 400, 800
    cols = ["a", "b"]
    X = pd.DataFrame(rng.normal(size=(n_int + n_ext, 2)), columns=cols).astype(np.float32)
    y = pd.Series((X["a"] + rng.normal(0, 1, n_int + n_ext) > 0).astype(np.int32))
    ts = pd.Series(list(pd.date_range("2026-08-01", periods=n_int, freq="h"))
                   + list(pd.date_range("2024-01-01", periods=n_ext, freq="h")))
    mask = np.r_[np.zeros(n_int, bool), np.ones(n_ext, bool)]
    _model, _cols, cal_x, _cal_y, metrics = train_model(X, y, cols, pd.Series(np.ones(n_int + n_ext)), ts, mask)
    # Calibration and validation come only from the bot's 400 rows.
    assert len(cal_x) < n_int
    assert int(metrics.get("validation_rows") or metrics.get("test_rows") or 0) <= n_int
