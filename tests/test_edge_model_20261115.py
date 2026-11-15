"""Edge model: track record + calibrated trees, decided on edge (15 Nov 2026)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml import edge_model as em


def test_point_in_time_prior_uses_only_earlier_rows():
    frame = pd.DataFrame({
        "created_at": pd.date_range("2026-11-01", periods=6, freq="h"),
        "strategy_name": ["A"] * 6, "asset_class_enc": [0] * 6, "timeframe": ["1h"] * 6,
        "target": [1, 1, 1, 0, 0, 0], "price_range": [0.02] * 6, "risk_amount": [0.01] * 6,
        "risk_reward_ratio": [2.0] * 6,
    })
    prior, edge = em.point_in_time_prior(frame)
    assert prior[0] == 0.5  # nothing earlier: the uninformed rate
    assert prior[3] > prior[1] > prior[0]  # wins so far raise it, row 3 cannot see its own loss
    assert abs(edge[3] - (prior[3] - 1 / 3)) < 1e-6
    skipped, _ = em.point_in_time_prior(frame, fit_only=[True] * 6)
    assert len(set(skipped)) == 1  # fit-only rows never build the track record


def test_decide_blends_and_compares_with_breakeven():
    metrics = {"decision_rule": "edge", "prior_blend": 0.5}
    values = {"segment_prior": 0.45, "price_range": 0.02, "risk_amount": 0.01}  # TP1 2R: break-even 1/3
    verdict = em.decide(metrics, 0.35, values)
    assert verdict["probability"] == 0.4 and verdict["passed"] and abs(verdict["edge"] - (0.4 - 1 / 3)) < 1e-6
    assert not em.decide(metrics, 0.10, {**values, "segment_prior": 0.2})["passed"]
    assert em.decide(metrics, 0.5, {"segment_prior": 0.0, "risk_reward_ratio": 2.0})["probability"] == 0.5


def test_edge_gate_needs_profit_across_folds():
    good = {"edge_walk_forward": {"folds": [{}] * 7, "mean_r": 0.25, "positive_share": 0.71}}
    assert em.edge_gate(good)[0]
    assert not em.edge_gate({"edge_walk_forward": {"folds": [{}] * 7, "mean_r": 0.05, "positive_share": 0.9}})[0]
    assert not em.edge_gate({"edge_walk_forward": {"folds": [{}] * 7, "mean_r": 0.3, "positive_share": 0.4}})[0]
    assert not em.edge_gate({"edge_walk_forward": {"folds": [{}] * 3, "mean_r": 0.3, "positive_share": 1.0}})[0]


def test_walk_forward_edge_finds_a_real_edge():
    rng = np.random.default_rng(5)
    n = 1500
    good_segment = rng.random(n) < 0.5
    y = pd.Series(np.where(good_segment, rng.random(n) < 0.6, rng.random(n) < 0.2).astype(int))
    X = pd.DataFrame({"segment_prior": np.where(good_segment, 0.55, 0.22), "noise": rng.normal(size=n),
                      "price_range": np.full(n, 0.02), "risk_amount": np.full(n, 0.01),
                      "risk_reward_ratio": np.full(n, 2.0)})
    ts = pd.Series(pd.date_range("2026-08-01", periods=n, freq="2h"))
    out = em.walk_forward_edge(X, y, np.arange(n), ts, trees=40,
                               params={"max_depth": 2, "learning_rate": 0.1, "objective": "binary:logistic",
                                       "eval_metric": "logloss", "random_state": 1})
    assert len(out["folds"]) >= 5 and out["mean_r"] > 0.3 and em.edge_gate({"edge_walk_forward": out})[0]


def test_live_prior_reads_the_class_keyed_snapshot(monkeypatch):
    from services import segment_evidence as se

    monkeypatch.setitem(se._LAST_SNAPSHOT, "value", {
        "class_segments": {em.segment_key("EMA Trend", 0, "1h"): {"n": 80, "wins": 48}},
        "class_totals": {"n": 1000, "wins": 300}})
    prior, g = em.live_prior("EMA Trend", 0.0, "1h")
    assert abs(g - 301 / 1002) < 1e-9 and 0.5 < prior < 0.6
    values = em.live_values({"strategy_name": "EMA Trend", "timeframe": "1h"},
                            {"asset_class_enc": 0.0, "price_range": 0.02, "risk_amount": 0.01})
    assert values["segment_prior"] == round(prior, 6) and values["prior_edge"] > 0
