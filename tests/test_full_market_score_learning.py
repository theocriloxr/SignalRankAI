from engine.score_calibration import (
    ScoreObservation, build_calibration_profile, calibrate_score, select_calibration_profile,
)
from engine.scoring import score_signal


def _observations(total: int = 300):
    rows = []
    for index in range(total):
        won = index % 2 == 0
        rows.append(ScoreObservation(
            score=80.0 if won else 20.0,
            won=won,
            source="canonical_issued" if index % 3 else "shadow_rejected",
            weight=1.0 if index % 3 else 0.6,
            observed_at=f"2026-01-{1 + index // 24:02d}T{index % 24:02d}:00:00",
            asset_class="crypto", timeframe="1h", strategy="breakout", regime="trending",
        ))
    return rows


def test_full_market_profile_is_monotonic_weighted_and_holdout_validated():
    profile = build_calibration_profile(
        _observations(), bins=5, minimum_observations=200, minimum_holdout=40,
    )

    probabilities = [row["probability"] for row in profile["buckets"]]
    assert probabilities == sorted(probabilities)
    assert profile["source_counts"] == {"shadow_rejected": 100, "canonical_issued": 200}
    assert profile["weighted_observations"] == 260.0
    assert profile["validated"] is True
    assert profile["validation"]["brier_calibrated"] < profile["validation"]["brier_raw"]
    assert calibrate_score(80.0, profile) > calibrate_score(20.0, profile)
    selected, key = select_calibration_profile(profile, {
        "asset_class": "crypto", "timeframe": "1h", "strategy_name": "breakout", "regime": "trending",
    })
    assert key == "asset_class=crypto|timeframe=1h"
    assert selected["validated"] is True


def test_sparse_profile_remains_shadow_only_and_unvalidated():
    profile = build_calibration_profile(_observations(20), minimum_observations=200, minimum_holdout=10)

    assert profile["validated"] is False
    assert profile["status"] == "collecting_evidence"
    assert profile["activation"] == "shadow_only"


def test_scoring_records_empirical_shadow_without_changing_live_score(monkeypatch):
    profile = build_calibration_profile(
        _observations(), bins=5, minimum_observations=200, minimum_holdout=40,
    )
    monkeypatch.setattr("engine.score_calibration.load_shadow_profile", lambda: profile)
    monkeypatch.setenv("SCORE_EMPIRICAL_CALIBRATION_SHADOW_ENABLED", "1")
    monkeypatch.setenv("SCORE_EMPIRICAL_CALIBRATION_ENABLED", "0")
    signal = {
        "asset": "BTCUSDT", "direction": "long", "entry": 100.0,
        "stop_loss": 95.0, "take_profit": 115.0, "confidence": 0.8,
        "ml_probability": 0.8, "confluence": 80.0, "volatility": 0.08,
        "regime_fit": 0.8,
    }

    live_score = score_signal(signal)

    assert signal["score_empirical_shadow"] is not None
    assert signal["score_calibration_method"] == "heuristic_weighted_v2"
    assert round(signal["score_calibrated"], 2) == live_score


def test_empirical_profile_cannot_activate_unless_validated(monkeypatch):
    profile = build_calibration_profile(_observations(20), minimum_observations=200, minimum_holdout=10)
    monkeypatch.setattr("engine.score_calibration.load_shadow_profile", lambda: profile)
    monkeypatch.setenv("SCORE_EMPIRICAL_CALIBRATION_SHADOW_ENABLED", "1")
    monkeypatch.setenv("SCORE_EMPIRICAL_CALIBRATION_ENABLED", "1")
    signal = {
        "asset": "EURUSD", "direction": "long", "entry": 1.1,
        "stop_loss": 1.09, "take_profit": 1.13, "confidence": 0.8,
        "ml_probability": 0.8, "confluence": 80.0, "volatility": 0.08,
    }

    score_signal(signal)

    assert signal["score_calibration_method"] == "heuristic_weighted_v2"
