from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.production_integrity import (
    evaluate_public_win_rate_claim,
    evaluate_signal_freshness,
    probability_for_public_display,
    signal_thesis_fingerprint,
)
from core.signal_quality_gate import evaluate_signal_quality
from core.outcome_ordering import evaluate_outcome_delivery
from services.profile_demand import aggregate_profile_demand
from services.user_intelligence import (
    merge_preference_payloads,
    personalize_signal_for_preferences,
    preferences_from_payload,
    signal_matches_preferences,
)


def _signal(**overrides):
    data = {
        "asset": "BTCUSDT",
        "asset_class": "crypto",
        "direction": "short",
        "timeframe": "1h",
        "entry": 63000.0,
        "stop_loss": 63200.0,
        "take_profit": [62750.0, 62500.0, 62400.0],
        "strategy_name": "EMA Trend",
        "regime": "trending",
        "score": 88.0,
        "market_session": "new_york",
    }
    data.update(overrides)
    return data


def test_freshness_rejects_old_one_hour_signal(monkeypatch):
    monkeypatch.setenv("PAPER_MAX_SIGNAL_AGE_1H_SECONDS", "1800")
    decision = evaluate_signal_freshness(
        timeframe="1h",
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=31),
        purpose="paper",
    )
    assert not decision.ok
    assert decision.reason == "signal_stale"


def test_thesis_fingerprint_collapses_tiny_repricing_and_timeframe(monkeypatch):
    monkeypatch.delenv("THESIS_FINGERPRINT_INCLUDE_TIMEFRAME", raising=False)
    a = signal_thesis_fingerprint(_signal(entry=63000, timeframe="15m"))
    b = signal_thesis_fingerprint(_signal(entry=63010, timeframe="1h"))
    assert a == b


def test_public_sixty_percent_claim_requires_statistical_evidence(monkeypatch):
    monkeypatch.setenv("PUBLIC_CLAIM_MIN_TERMINAL_SAMPLE", "200")
    monkeypatch.setenv("PUBLIC_CLAIM_MIN_UNIQUE_THESES", "100")
    monkeypatch.setenv("PUBLIC_CLAIM_MIN_TERMINAL_COVERAGE", "0.95")
    weak = evaluate_public_win_rate_claim(
        wins=12, losses=8, delivered=40, resolved=20, unique_theses=10,
    )
    assert not weak.allowed
    strong = evaluate_public_win_rate_claim(
        wins=150, losses=50, delivered=205, resolved=200, unique_theses=160,
    )
    assert strong.allowed
    assert strong.lower_bound >= 0.60


def test_public_probability_hides_uncalibrated_score(monkeypatch):
    monkeypatch.setenv("ML_PROBABILITY_DISPLAY_REQUIRES_CALIBRATION", "1")
    hidden = probability_for_public_display({"ml_probability": 0.97})
    assert hidden.probability is None
    shown = probability_for_public_display({
        "ml_probability_calibrated": 0.63,
        "ml_calibration_version": "iso:model-12",
        "ml_calibration_validated": True,
        "ml_calibration_validation_rows": 250,
        "ml_calibration_brier": 0.16,
        "ml_calibration_ece": 0.04,
    })
    assert shown.calibrated is True
    assert shown.probability == pytest.approx(0.63)


def test_quality_gate_rejects_invalid_geometry_and_accepts_evidence():
    bad = evaluate_signal_quality(_signal(stop_loss=62000.0))
    assert not bad.ok
    assert "short_stop_not_above_entry" in bad.reasons
    good = evaluate_signal_quality(_signal())
    assert good.ok
    assert good.final_rr >= 2.0


def test_outcome_delivery_is_monotonic():
    assert evaluate_outcome_delivery("tp2", highest_delivered_rank=10).allowed
    assert not evaluate_outcome_delivery("tp1", highest_delivered_rank=20).allowed
    assert not evaluate_outcome_delivery("tp2", terminal_already_delivered=True).allowed


def test_legacy_and_modern_profile_are_merged():
    merged = merge_preference_payloads(
        {"preferred_assets": ["BTCUSDT"], "trade_profile": "day"},
        {"risk_per_trade_pct": 0.5, "execution_mode": "copy"},
        {"profile": "swing"},
    )
    prefs = preferences_from_payload(merged)
    assert prefs.trade_profile == "day"
    assert prefs.risk_profile == "conservative"
    assert prefs.execution_mode == "copy_trade"
    assert prefs.preferred_assets == ("BTCUSDT",)


def test_profile_filters_and_personalizes_delivery():
    prefs = preferences_from_payload({
        "trade_profile": "day",
        "risk_profile": "balanced",
        "asset_classes": ["crypto"],
        "preferred_assets": ["BTCUSDT"],
        "preferred_timeframes": ["1h"],
        "sessions": ["new_york"],
        "min_signal_score": 80,
    })
    allowed, reason = signal_matches_preferences(_signal(), prefs)
    assert allowed, reason
    denied, reason = signal_matches_preferences(_signal(asset="ETHUSDT"), prefs)
    assert not denied and reason == "not_preferred_asset"
    personalized = personalize_signal_for_preferences(_signal(), prefs)
    assert personalized["delivery_profile_verified"] is True
    assert personalized["personalized_rank_score"] > 88.0


def test_profile_demand_shapes_discovered_universe_without_injecting_assets():
    records = {
        1: {"modern": {"asset_classes": ["crypto"], "preferred_assets": ["SOLUSDT"], "preferred_timeframes": ["1h"]}},
        2: {"modern": {"asset_classes": ["fx"], "preferred_timeframes": ["4h"]}},
    }
    snapshot = aggregate_profile_demand(records)
    assert snapshot.active_profiles == 2
    assert snapshot.accepts_asset("BTCUSDT")
    assert snapshot.accepts_asset("EURUSD")
    assert snapshot.asset_priority("SOLUSDT") > snapshot.asset_priority("BTCUSDT")
    assert snapshot.timeframes_for(["15m", "1h"], asset_class="crypto")[0] == "1h"
