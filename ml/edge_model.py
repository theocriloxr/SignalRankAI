"""Edge model (feature schema v7, 11-15 Nov 2026): track record + calibrated trees, decided on edge.

Research (purged walk-forward on the bot's own tracked setups, 4,072 rows, 7 folds):
every model that ranked setups by win probability lost money (-0.36R at best), because a
high hit rate came with a close, cheap TP1. What held up out of sample was each
strategy's own track record in its asset class and timeframe, and deciding on *edge*:
the estimated chance of TP1 minus that setup's break-even rate 1/(1+R).

* track record only, edge > 0: +0.23R per trade on average (worst fold -0.13R);
* 50/50 blend of the track record and calibrated trees, edge > 0: +0.25R (worst -0.18R),
  the best average, and the model this module serves.

Independent confirmation (15 Nov 2026, one-off container, read-only): 4,137 rows (3,998 own
setups + public-history replays, Fear & Greed, FRED HY spread, CFTC COT, regime features).
32 configurations were compared only on 6 walk-forward folds inside the first 85 % of time;
the top ten all averaged +0.19R to +0.23R with 4 of 6 folds positive. The best (prior
weight 0.3, depth 2) was then scored once on the untouched last 15 % (600 setups): taking
every setup -0.23R, track record alone +0.08R (198 trades), this model +0.25R (83 trades).
Hence the default prior weight is 0.3 (``ML_EDGE_PRIOR_BLEND``).

Pieces:

* ``segment_prior``: the strategy x asset class x timeframe TP1 rate, shrunk toward the
  overall rate with ``PRIOR_STRENGTH`` (20) pseudo-trades. Training computes it point in
  time (earlier rows only); live scoring reads the setup-evidence snapshot's
  ``class_segments`` (services/segment_evidence.py).
* ``prior_edge``: ``segment_prior`` minus the setup's break-even rate.
* decision (blend default 0.3): p = blend * segment_prior + (1 - blend) * calibrated model probability;
  take the setup when p - 1/(1 + R_tp1) > ``ML_EDGE_MIN`` (0).
* promotion (``edge_gate``): mean walk-forward R >= ``ML_EDGE_MIN_MEAN_R`` (0.10) with at
  least ``ML_EDGE_MIN_POSITIVE_FOLD_SHARE`` (0.6) of folds positive. Accuracy is not the
  goal of this model type; profit on unseen windows is. Leakage, label-noise,
  overfitting and calibration checks still apply, and the forward proof and the owner's
  /ml_candidate_promote CONFIRM are unchanged.
"""
from __future__ import annotations

import os
from typing import Any

PRIOR_STRENGTH = 20.0
DECISION_RULE = "edge"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def segment_key(strategy: Any, asset_class_enc: Any, timeframe: Any) -> str:
    try:
        cls = str(int(round(float(asset_class_enc))))
    except (TypeError, ValueError):
        cls = "?"
    return f"{str(strategy or '').strip().lower()}|{cls}|{str(timeframe or '').strip().lower()}"


def shrunk_rate(wins: float, n: float, global_rate: float, strength: float = PRIOR_STRENGTH) -> float:
    return (float(wins) + strength * float(global_rate)) / (float(n) + strength)


def breakeven(reward_r: Any) -> float:
    try:
        r = float(reward_r)
    except (TypeError, ValueError):
        r = 0.0
    r = min(10.0, max(0.2, r)) if r > 0 else 2.0
    return 1.0 / (1.0 + r)


def tp1_reward(values: dict[str, Any]) -> float:
    """TP1 reward/risk from the feature contract (price_range / risk_amount), else risk_reward_ratio."""
    try:
        price_range, risk = float(values.get("price_range") or 0), float(values.get("risk_amount") or 0)
        if risk > 0 and 0 < price_range < 0.9:
            return price_range / risk
    except (TypeError, ValueError):
        pass
    try:
        return float(values.get("risk_reward_ratio") or 2.0)
    except (TypeError, ValueError):
        return 2.0


# --- live -------------------------------------------------------------------------------


def live_prior(strategy: Any, asset_class_enc: Any, timeframe: Any) -> tuple[float, float]:
    """(segment_prior, global_rate) from the latest setup-evidence snapshot; (0, 0) without one."""
    try:
        from services.segment_evidence import last_snapshot

        snap = last_snapshot() or {}
    except Exception:
        snap = {}
    cells = snap.get("class_segments") or {}
    totals = snap.get("class_totals") or {}
    n_all, w_all = float(totals.get("n") or 0), float(totals.get("wins") or 0)
    if n_all <= 0:
        return 0.0, 0.0
    global_rate = (w_all + 1.0) / (n_all + 2.0)
    cell = cells.get(segment_key(strategy, asset_class_enc, timeframe)) or {}
    return shrunk_rate(cell.get("wins") or 0, cell.get("n") or 0, global_rate), global_rate


def live_values(signal: dict[str, Any], values: dict[str, Any]) -> dict[str, float]:
    prior, _g = live_prior(signal.get("strategy_name") or signal.get("strategy"), values.get("asset_class_enc"),
                           signal.get("timeframe"))
    if prior <= 0:
        return {"segment_prior": 0.0, "prior_edge": 0.0}
    return {"segment_prior": round(prior, 6), "prior_edge": round(prior - breakeven(tp1_reward(values)), 6)}


# --- decision --------------------------------------------------------------------------


def is_edge_model(metrics: dict[str, Any] | None) -> bool:
    return str((metrics or {}).get("decision_rule") or "") == DECISION_RULE


def decide(metrics: dict[str, Any], calibrated_probability: float, values: dict[str, Any]) -> dict[str, Any]:
    blend = min(1.0, max(0.0, float(metrics.get("prior_blend", 0.3) or 0.0)))
    prior = float(values.get("segment_prior") or 0.0)
    if prior <= 0:  # no track record available: the model's own estimate only
        blend = 0.0
    p = blend * prior + (1.0 - blend) * float(calibrated_probability)
    reward = tp1_reward(values)
    edge = p - breakeven(reward)
    minimum = _env_float("ML_EDGE_MIN", float(metrics.get("edge_min", 0.0) or 0.0))
    return {"probability": round(p, 6), "edge": round(edge, 6), "reward_r": round(reward, 4),
            "passed": edge > minimum, "threshold": minimum}


# --- training --------------------------------------------------------------------------


def point_in_time_prior(frame: Any, *, fit_only: Any = None) -> tuple[list[float], list[float]]:
    """(segment_prior, prior_edge) per row, using only rows that happened earlier."""
    import numpy as np
    import pandas as pd

    n = len(frame)
    stamps = pd.to_datetime(frame["created_at"], errors="coerce", utc=True).fillna(pd.Timestamp("1970-01-01", tz="UTC"))
    order = np.argsort(stamps.values, kind="stable")
    keys = [segment_key(s, c, t) for s, c, t in zip(frame["strategy_name"].fillna("") if "strategy_name" in frame else [""] * n,
                                                   frame["asset_class_enc"], frame["timeframe"].fillna(""))]
    target = frame["target"].astype(int).to_numpy()
    skip = np.zeros(n, dtype=bool) if fit_only is None else np.asarray(fit_only, dtype=bool)
    prior = np.zeros(n)
    wins: dict[str, int] = {}
    counts: dict[str, int] = {}
    total_w = total_n = 0
    for i in order:
        g = (total_w + 1.0) / (total_n + 2.0)
        prior[i] = shrunk_rate(wins.get(keys[i], 0), counts.get(keys[i], 0), g)
        if not skip[i]:
            counts[keys[i]] = counts.get(keys[i], 0) + 1
            wins[keys[i]] = wins.get(keys[i], 0) + int(target[i])
            total_n += 1
            total_w += int(target[i])
    rewards = [tp1_reward({"price_range": pr, "risk_amount": ra, "risk_reward_ratio": rr})
               for pr, ra, rr in zip(frame.get("price_range", [0] * n), frame.get("risk_amount", [0] * n),
                                     frame.get("risk_reward_ratio", [2.0] * n))]
    edge = [float(p) - breakeven(r) for p, r in zip(prior, rewards)]
    return [round(float(p), 6) for p in prior], [round(e, 6) for e in edge]


def walk_forward_edge(X: Any, y: Any, ordered_idx: Any, timestamps: Any, *, params: dict, trees: int,
                      blend: float = 0.5, embargo_hours: float = 24.0, folds: int = 7,
                      fit_only_idx: Any = None, sample_weights: Any = None) -> dict[str, Any]:
    """Purged walk-forward of the edge rule; realised R per fold at each setup's own TP1.

    Folds are cut over ``ordered_idx`` (the bot's own rows) only, so every test window is real
    tracked setups. 16 Nov 2026: each fold now trains the way the shipped model does: fit-only
    rows (public-history replay, user ideas) dated before the fold's embargo line join that
    fold's fit window, and ``sample_weights`` apply to the fit rows. Before this the gate scored
    an own-rows, unweighted model while the shipped model was weighted and replay-augmented.
    """
    import numpy as np
    import pandas as pd
    import xgboost as xgb
    from sklearn.isotonic import IsotonicRegression

    out: dict[str, Any] = {"folds": []}
    n = len(ordered_idx)
    if n < 600 or timestamps is None or "segment_prior" not in X.columns:
        return out
    stamp = pd.to_datetime(pd.Series(np.asarray(timestamps)), errors="coerce")
    extra_idx = None if fit_only_idx is None else np.asarray(fit_only_idx, dtype=int)
    weights = None if sample_weights is None else np.asarray(sample_weights, dtype=float)
    if weights is not None and len(weights) != len(X):
        weights = None
    for cut in np.linspace(0.50, 0.85, folds):
        a, b = int(n * cut), min(n, int(n * (cut + 0.08)))
        test = ordered_idx[a:b]
        if len(test) < 60:
            continue
        t0 = stamp.iloc[test].min()
        train = ordered_idx[:a][(stamp.iloc[ordered_idx[:a]] <= t0 - pd.Timedelta(hours=embargo_hours)).to_numpy()]
        if len(train) < 400:
            continue
        fit, cal = train[: int(len(train) * 0.8)], train[int(len(train) * 0.8):]
        if extra_idx is not None and len(extra_idx):
            fit = np.concatenate([extra_idx[(stamp.iloc[extra_idx] <= t0 - pd.Timedelta(hours=embargo_hours))
                                            .to_numpy()], fit])
        if len(set(y.iloc[fit])) < 2:
            continue
        model = xgb.XGBClassifier(**{**params, "n_estimators": int(trees), "early_stopping_rounds": None})
        fit_kwargs = {} if weights is None else {"sample_weight": weights[fit]}
        model.fit(X.iloc[fit], y.iloc[fit], **fit_kwargs)
        p = model.predict_proba(X.iloc[test])[:, 1]
        if len(set(y.iloc[cal])) == 2:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
            iso.fit(model.predict_proba(X.iloc[cal])[:, 1], y.iloc[cal])
            p = iso.predict(p)
        prior = X["segment_prior"].to_numpy()[test]
        blended = blend * prior + (1 - blend) * p
        reward = np.array([tp1_reward(row) for row in X.iloc[test][["price_range", "risk_amount", "risk_reward_ratio"]]
                           .to_dict("records")]) if {"price_range", "risk_amount", "risk_reward_ratio"} <= set(X.columns) \
            else np.full(len(test), 2.0)
        edge = blended - np.array([breakeven(r) for r in reward])
        take = edge > 0
        yt = y.iloc[test].to_numpy()
        realised = float(np.where(yt[take] == 1, reward[take], -1.0).mean()) if take.any() else 0.0
        out["folds"].append({"train": int(len(train)), "test": int(len(test)), "trades": int(take.sum()),
                             "expected_r": round(realised, 4)})
    if out["folds"]:
        values = [f["expected_r"] for f in out["folds"] if f["trades"] > 0]
        if values:
            out.update(mean_r=round(float(np.mean(values)), 4), worst_r=round(float(np.min(values)), 4),
                       positive_share=round(sum(1 for v in values if v > 0) / len(values), 3),
                       trades=int(sum(f["trades"] for f in out["folds"])))
    return out


def edge_gate(metrics: dict[str, Any]) -> tuple[bool, str]:
    wf = metrics.get("edge_walk_forward") or {}
    if len(wf.get("folds") or []) < 5 or "mean_r" not in wf:
        return False, "edge_walk_forward_insufficient"
    if float(wf["mean_r"]) < _env_float("ML_EDGE_MIN_MEAN_R", 0.10):
        return False, f"edge_mean_r {wf['mean_r']}"
    if float(wf.get("positive_share") or 0) < _env_float("ML_EDGE_MIN_POSITIVE_FOLD_SHARE", 0.6):
        return False, f"edge_positive_share {wf.get('positive_share')}"
    return True, "edge_passed"
