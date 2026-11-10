"""Regression tests for two training-quality fixes (10 Nov 2026).

1. Point-in-time candles: live-delivery training rows recompute velocity, ATR,
   relative volume, ADX and higher-timeframe trend from market_candles. The old
   open-time cutoff included the bar that was still forming at signal time, with
   the final (post-signal) OHLCV it was later overwritten with.
2. Payoff-aware expectancy: wins are TP1 hits, so a win is worth that signal's
   TP1 R, not a fixed 2R, when choosing the threshold and gating promotion.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from ml.metrics import evaluate_classification, expected_r_utility
from ml.train_model import (
    EXPECTED_R_BASIS_FIXED,
    EXPECTED_R_BASIS_TP1,
    _candle_availability_times,
    _champion_comparison_gate,
    _point_in_time_slice,
    _select_classification_threshold,
    _tp1_win_r,
)

HOUR_MS = 3_600_000


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


# --- 1. point-in-time candles -------------------------------------------------


def test_forming_bar_at_signal_time_is_excluded():
    opens = [_ms("2026-11-10T08:00:00"), _ms("2026-11-10T09:00:00"), _ms("2026-11-10T10:00:00")]
    closes = [o + HOUR_MS - 1 for o in opens]  # Binance-style close_time
    available = _candle_availability_times(opens, closes, 3600)
    signal_at = _ms("2026-11-10T10:00:05")  # emitted just after the 09:00 bar closed

    start, stop = _point_in_time_slice(available, signal_at, limit=80)

    assert stop == 2, "the 10:00 bar was still forming at 10:00:05 and must not be used"
    assert (start, stop) == (0, 2)
    # The legacy open-time cutoff would have included it.
    legacy_stop = int(np.searchsorted(opens, signal_at, side="right"))
    assert legacy_stop == 3


def test_missing_or_insane_close_times_fall_back_to_open_plus_one_bar():
    opens = [0, HOUR_MS, 2 * HOUR_MS]
    available = _candle_availability_times(opens, [None, "bad", 10 * HOUR_MS], 3600)
    assert available == [HOUR_MS - 1, 2 * HOUR_MS - 1, 3 * HOUR_MS - 1]


def test_availability_is_monotonic_for_bisect():
    opens = [0, HOUR_MS, 2 * HOUR_MS]
    available = _candle_availability_times(opens, [HOUR_MS - 1, HOUR_MS - 5, 3 * HOUR_MS - 1], 3600)
    assert available == sorted(available)


def test_legacy_open_time_cutoff_can_be_restored(monkeypatch):
    monkeypatch.setenv("ML_TRAINING_CLOSED_CANDLES_ONLY", "false")
    opens = [0, HOUR_MS]
    assert _candle_availability_times(opens, [HOUR_MS - 1, 2 * HOUR_MS - 1], 3600) == opens


def test_limit_keeps_newest_closed_bars():
    available = [i * HOUR_MS for i in range(1, 11)]
    assert _point_in_time_slice(available, 5 * HOUR_MS, limit=3) == (2, 5)


# --- 2. payoff-aware expectancy ----------------------------------------------


def test_tp1_win_r_uses_geometry_and_falls_back_safely():
    frame = pd.DataFrame(
        {
            # 1R, 1.5R, missing target (price_range ~ 1.0), zero risk
            "price_range": [0.01, 0.015, 1.0, 0.02],
            "risk_amount": [0.01, 0.01, 0.01, 0.0],
        }
    )
    assert _tp1_win_r(frame).tolist() == pytest.approx([1.0, 1.5, 2.0, 2.0])


def test_tp1_win_r_disabled_or_unavailable_keeps_legacy(monkeypatch):
    assert _tp1_win_r(pd.DataFrame({"price_range": [0.01]})) is None
    monkeypatch.setenv("ML_PAYOFF_AWARE_EXPECTANCY", "false")
    assert _tp1_win_r(pd.DataFrame({"price_range": [0.01], "risk_amount": [0.01]})) is None


def test_expected_r_utility_pays_each_wins_own_tp1():
    y, p = [1, 0, 1], [0.9, 0.9, 0.9]
    assert expected_r_utility(y, p, decision_threshold=0.5)["expected_r"] == pytest.approx(1.0)
    paid = expected_r_utility(y, p, decision_threshold=0.5, win_r=[1.0, 3.0, 1.5])
    assert paid["expected_r"] == pytest.approx(0.5)  # (1.0 + 1.5 - 1) / 3


def test_evaluation_report_carries_payoff_aware_expected_r():
    report = evaluate_classification([1, 0, 1, 0], [1, 1, 1, 0], [0.9, 0.8, 0.7, 0.1],
                                     decision_threshold=0.5, win_r=[1.0, 1.0, 1.0, 1.0])
    assert report.expected_r == pytest.approx(1.0 / 3, abs=1e-3)


def _bins(*bins):
    """(count, probability, win_rate, tp1_r) bins -> labels, probabilities, payoffs."""
    probabilities, labels, payoffs = [], [], []
    for count, probability, win_rate, tp1_r in bins:
        wins = int(round(count * win_rate))
        for index in range(count):
            probabilities.append(probability)
            labels.append(1 if index < wins else 0)
            payoffs.append(tp1_r)
    return np.array(labels), np.array(probabilities), np.array(payoffs)


def _realised_r(labels, probabilities, payoffs, threshold):
    chosen = probabilities >= threshold
    gained = float(payoffs[chosen & (labels == 1)].sum())
    lost = int((chosen & (labels == 0)).sum())
    return (gained - lost) / max(1, int(chosen.sum()))


def test_threshold_follows_real_tp1_sizes_not_win_rate_alone():
    # Highest-probability setups win 60% but TP1 is only 0.5R (they lose money);
    # mid setups win 45% with a 3R TP1 (they make money).
    labels, probabilities, payoffs = _bins((300, 0.85, 0.60, 0.5), (300, 0.55, 0.45, 3.0), (600, 0.20, 0.20, 1.0))

    legacy = _select_classification_threshold(labels, probabilities)
    aware = _select_classification_threshold(labels, probabilities, win_r=payoffs)

    assert _realised_r(labels, probabilities, payoffs, legacy) < 0.0  # the fixed-2R pick loses
    assert _realised_r(labels, probabilities, payoffs, aware) > 0.3
    assert aware < legacy


def test_one_r_targets_at_42_percent_no_longer_look_profitable():
    labels, probabilities, payoffs = _bins((500, 0.8, 0.42, 1.0), (500, 0.3, 0.30, 1.0))
    predicted = (probabilities >= 0.5).astype(int)

    legacy = evaluate_classification(labels, predicted, probabilities, decision_threshold=0.5)
    aware = evaluate_classification(labels, predicted, probabilities, decision_threshold=0.5, win_r=payoffs)

    assert legacy.expected_r > 0.05  # would have passed ML_MIN_EXPECTED_R
    assert aware.expected_r < 0.0  # the truth at 1R: 0.42 - 0.58


def test_mismatched_payoff_length_is_ignored():
    labels, probabilities, _ = _bins((300, 0.85, 0.60, 0.5), (300, 0.55, 0.45, 3.0), (600, 0.20, 0.20, 1.0))
    assert _select_classification_threshold(labels, probabilities, win_r=[1.0, 2.0]) == pytest.approx(
        _select_classification_threshold(labels, probabilities)
    )


def _metrics(**overrides):
    base = {"auc": 0.70, "pr_auc": 0.60, "balanced_accuracy": 0.62, "expected_r": 0.30}
    base.update(overrides)
    return base


def test_champion_gate_does_not_compare_expected_r_across_payoff_bases(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "true")
    legacy_champion = _metrics(expected_r=0.60)  # scored on the old fixed 2R
    candidate = _metrics(expected_r=0.10, expected_r_basis=EXPECTED_R_BASIS_TP1)

    accepted, evidence = _champion_comparison_gate(candidate, tmp_path / "missing.json",
                                                   champion_metrics=legacy_champion)

    assert accepted is True
    assert "expected_r" not in evidence["compared"]
    assert evidence["expected_r_not_compared"]["champion"] == EXPECTED_R_BASIS_FIXED


def test_champion_gate_still_compares_expected_r_on_the_same_basis(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "true")
    champion = _metrics(expected_r=0.60, expected_r_basis=EXPECTED_R_BASIS_TP1)
    candidate = _metrics(expected_r=0.10, expected_r_basis=EXPECTED_R_BASIS_TP1)

    accepted, evidence = _champion_comparison_gate(candidate, tmp_path / "missing.json",
                                                   champion_metrics=champion)

    assert accepted is False
    assert "expected_r" in evidence["regressions"]


def test_live_features_drop_a_still_forming_tail_bar():
    import time as _time

    from ml.features import closed_candles

    now = int(_time.time() * 1000)
    closed = {"open_time_ms": now - 2 * HOUR_MS, "close": 1.0}
    forming = {"open_time_ms": now - HOUR_MS // 2, "close": 2.0}
    assert closed_candles([closed, forming], "1h") == [closed]
    assert closed_candles([closed, {"is_final": True, "close": 3.0}], "1h")[-1]["close"] == 3.0
    assert closed_candles([{"close": 1.0}, {"close": 2.0}], "1h")[-1]["close"] == 2.0  # no timing: unchanged
