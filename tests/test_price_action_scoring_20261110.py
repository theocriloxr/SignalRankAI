"""Price-action evidence is graded (owner, 10 Nov 2026: "proper scoring, not that they all turn to 0/100")."""
from __future__ import annotations

import numpy as np

from core.candle_evidence import assess_candle_evidence


def _bar(i, o, h, l, c, v=100.0):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "timestamp": 1_700_000_000_000 + i * 3_600_000}


def test_a_pullback_into_support_is_not_scored_zero():
    bars = [_bar(i, 100 + i * 0.2, 100.6 + i * 0.2, 99.6 + i * 0.2, 100.3 + i * 0.2) for i in range(40)]
    # three red candles pulling back to the prior swing low area, last one closing near its high
    bars += [_bar(40, 108.2, 108.3, 107.0, 107.2), _bar(41, 107.2, 107.3, 106.2, 106.4),
             _bar(42, 106.4, 106.9, 105.9, 106.7)]
    long_score = assess_candle_evidence(bars, focus_index=42, direction="long").evidence_score_pct
    assert long_score >= 35  # the old binary score gave textbook pullbacks 0/100


def test_scores_spread_across_the_range_and_never_pile_up_at_zero():
    rng = np.random.default_rng(5)
    p, bars = 100.0, []
    for i in range(1500):
        o = p
        p *= 1 + rng.normal(0, 0.004)
        h, l = max(o, p) * (1 + abs(rng.normal(0, 0.002))), min(o, p) * (1 - abs(rng.normal(0, 0.002)))
        bars.append(_bar(i, o, h, l, p, float(rng.uniform(50, 150))))
    scores = np.array([assess_candle_evidence(bars[:i + 1], focus_index=i, direction=d).evidence_score_pct
                       for i in range(60, 1490, 5) for d in ("long", "short")])
    assert (scores == 0).mean() < 0.01
    assert np.percentile(scores, 90) - np.percentile(scores, 10) > 30  # it discriminates


def test_the_trade_direction_matters():
    bars = [_bar(i, 100 + i * 0.3, 100.5 + i * 0.3, 99.8 + i * 0.3, 100.3 + i * 0.3, 100) for i in range(40)]
    bars.append(_bar(40, 112.0, 113.6, 111.9, 113.5, 220))  # strong breakout candle on volume
    long_score = assess_candle_evidence(bars, focus_index=40, direction="long").evidence_score_pct
    short_score = assess_candle_evidence(bars, focus_index=40, direction="short").evidence_score_pct
    assert long_score >= 70 and short_score <= 30


def test_the_score_is_the_weighted_mean_of_its_shown_components():
    bars = [_bar(i, 100 + i * 0.3, 100.5 + i * 0.3, 99.8 + i * 0.3, 100.3 + i * 0.3, 100) for i in range(40)]
    bars.append(_bar(40, 112.0, 113.6, 111.9, 113.5, 220))
    ev = assess_candle_evidence(bars, focus_index=40, direction="long")
    parts = ev.evidence_components
    weights = {"body": .20, "wick": .15, "close": .20, "location": .20, "structure": .15, "volume": .10,
               "follow_through": .15}
    expected = sum(weights[k] * v for k, v in parts.items()) / sum(weights[k] for k in parts)
    assert abs(ev.evidence_score_pct - expected) < 0.2  # calculated from the parts, nothing fixed
    assert {"body", "wick", "close", "location", "structure", "volume"} <= set(parts)
    from signalrank_telegram.tier_signal_formatter import _candle_price_action_lines

    text = "\n".join(_candle_price_action_lines({"candle_evidence": {**ev.as_dict(), "alignment": "supportive"}}))
    assert "Score parts: Body" in text
