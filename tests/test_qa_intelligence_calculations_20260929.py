from __future__ import annotations

from pathlib import Path

import pytest

from engine.signal_calculations import (
    calculate_expected_loss,
    calculate_expected_profit,
    calculate_pips,
    calculate_risk_reward,
    calculate_rr_ladder,
    format_enhanced_signal_data,
)


def test_target_dicts_are_normalized_for_profit_and_rr() -> None:
    signal = {
        "asset": "EURUSD",
        "direction": "long",
        "entry": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": [
            {"price": 1.1050},
            {"target": 1.1100},
            {"tp": 1.1150},
        ],
        "risk_pct": 1.0,
    }
    assert calculate_expected_profit(signal) == pytest.approx((0.005 / 1.1) * 100)
    assert calculate_expected_loss(signal) == pytest.approx((-0.005 / 1.1) * 100)
    ladder = calculate_rr_ladder(signal)
    assert ladder["target_rrs"] == pytest.approx([1.0, 2.0, 3.0])
    assert ladder["tp1_rr"] == pytest.approx(1.0)
    assert ladder["final_rr"] == pytest.approx(3.0)
    assert calculate_risk_reward(signal) == pytest.approx(1.0)


def test_invalid_direction_or_target_geometry_never_fabricates_profit() -> None:
    wrong_way = {
        "direction": "long",
        "entry": 100,
        "stop_loss": 95,
        "take_profit": 90,
    }
    unknown = {
        "direction": "sideways",
        "entry": 100,
        "stop_loss": 95,
        "take_profit": 110,
    }
    assert calculate_expected_profit(wrong_way) is None
    assert calculate_expected_profit(unknown) is None
    assert calculate_expected_loss(unknown) is None
    assert calculate_rr_ladder(wrong_way)["tp1_rr"] is None


def test_fx_pips_support_canonical_symbols_without_slashes() -> None:
    assert calculate_pips("EURUSD", 1.1000, 1.1050) == pytest.approx(50.0)
    assert calculate_pips("EUR/USD", 1.1000, 1.1050) == pytest.approx(50.0)
    assert calculate_pips("USDJPY", 150.00, 150.50) == pytest.approx(50.0)
    assert calculate_pips("BTCUSD", 60000, 60100) is None
    assert calculate_pips("XAUUSD", 2500, 2510) is None


def test_enhanced_projection_exposes_tp1_final_rr_and_pips() -> None:
    signal = {
        "asset": "GBPUSD",
        "direction": "short",
        "entry": 1.3000,
        "stop_loss": 1.3050,
        "take_profit": [1.2950, 1.2900, 1.2850],
        "risk_pct": 0.5,
    }
    enhanced = format_enhanced_signal_data(signal)
    assert enhanced["rr_tp1"] == pytest.approx(1.0)
    assert enhanced["rr_final"] == pytest.approx(3.0)
    assert enhanced["rr_targets"] == pytest.approx([1.0, 2.0, 3.0])
    assert enhanced["pips_to_tp"] == pytest.approx(50.0)
    assert enhanced["pips_to_sl"] == pytest.approx(50.0)
    assert enhanced["position_size_unit"] == "asset_units"


def test_web_and_telegram_use_canonical_enhanced_projection() -> None:
    root = Path(__file__).resolve().parents[1]
    web = (root / "web" / "platform_api.py").read_text(encoding="utf-8")
    telegram = (root / "signalrank_telegram" / "formatter.py").read_text(encoding="utf-8")
    assert "format_enhanced_signal_data(payload)" in web
    assert 'payload["rr_tp1"] = enhanced.get("rr_tp1")' in web
    assert 'payload["rr_final"] = enhanced.get("rr_final")' in web
    assert "R/R Final" in telegram


def test_ai_reviewers_receive_proof_backed_context_without_tier_bias() -> None:
    root = Path(__file__).resolve().parents[1]
    openai = (root / "services" / "openai_ai.py").read_text(encoding="utf-8")
    gemini = (root / "services" / "gemini_ml.py").read_text(encoding="utf-8")
    for source in (openai, gemini):
        assert "historical_sample_size" in source
        assert "historical_win_rate" in source
        assert "historical_avg_r" in source
        assert "historical_profit_factor" in source
        assert "rr_final" in source
    signal_context = openai[
        openai.index("def _signal_context"):
        openai.index("async def review_signal")
    ]
    assert '"tier"' not in signal_context


def test_direction_arbitration_uses_provider_neutral_router_only() -> None:
    root = Path(__file__).resolve().parents[1]
    controller = (root / "engine" / "signal_controller.py").read_text(encoding="utf-8")
    router = (root / "services" / "ai_review_router.py").read_text(encoding="utf-8")
    assert "from services.ai_review_router import choose_direction as _choose_direction" in controller
    assert "generativelanguage.googleapis.com" not in controller
    assert "urllib.request" not in controller
    assert "async def choose_direction(" in router
    assert "AI_DIRECTION_MODE" in router


def test_historical_context_is_enriched_before_final_ai_review() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    history = engine.index("get_live_performance_context")
    review = engine.index("gemini_ok, gemini_score, gemini_reason", history)
    assert history < review
    assert 'sig["historical_sample_size"]' in engine[history:review]
    assert 'sig["live_expectancy"]' in engine[history:review]


def test_invalid_geometry_does_not_resurrect_cached_rr() -> None:
    signal = {
        "direction": "long",
        "entry": 100,
        "stop_loss": 95,
        "take_profit": 90,
        "rr_ratio": 9.9,
        "rr_estimate": 9.9,
    }
    assert calculate_risk_reward(signal) is None


def test_position_sizing_rejects_invalid_geometry_and_direction() -> None:
    from engine.signal_calculations import calculate_position_size

    assert calculate_position_size(
        {"direction": "sideways", "entry": 100, "stop_loss": 95},
        account_balance=10_000,
        risk_pct=1,
    ) is None
    assert calculate_position_size(
        {"direction": "long", "entry": 100, "stop_loss": 105},
        account_balance=10_000,
        risk_pct=1,
    ) is None
    assert calculate_position_size(
        {"direction": "short", "entry": 100, "stop_loss": 105},
        account_balance=10_000,
        risk_pct=1,
    ) == pytest.approx(20.0)


def test_signal_age_respects_timezone_offset_and_never_goes_negative(monkeypatch) -> None:
    import engine.signal_calculations as calculations
    from datetime import datetime

    monkeypatch.setattr(calculations, "now_utc_naive", lambda: datetime(2026, 9, 29, 1, 0, 0))
    assert calculations.calculate_signal_age_minutes(
        {"created_at": "2026-09-29T02:00:00+01:00"}
    ) == 0
    assert calculations.calculate_signal_age_minutes(
        {"created_at": "2026-09-29T03:00:00+01:00"}
    ) == 0


def test_swing_profile_covers_intermediate_higher_timeframes() -> None:
    from services.trade_profiles import get_trade_profile, infer_trade_profile

    swing = get_trade_profile("swing")
    for timeframe in ("2h", "4h", "6h", "8h", "12h", "1d"):
        assert timeframe in swing.timeframes
        assert infer_trade_profile({"timeframe": timeframe}) == "swing"


def test_time_to_target_is_explicitly_heuristic_not_calibrated() -> None:
    from services.trade_profiles import estimate_time_to_target

    projection = estimate_time_to_target(
        {
            "direction": "long",
            "timeframe": "6h",
            "entry": 100,
            "stop_loss": 98,
            "take_profit": [104],
            "atr": 2,
        },
        "swing",
    )
    assert projection["probability_model"] == "heuristic_atr_time"
    assert projection["probabilities_calibrated"] is False


def test_ai_context_includes_current_quality_components() -> None:
    root = Path(__file__).resolve().parents[1]
    openai = (root / "services" / "openai_ai.py").read_text(encoding="utf-8")
    gemini = (root / "services" / "gemini_ml.py").read_text(encoding="utf-8")
    for source in (openai, gemini):
        assert "score_components" in source
        assert "confidence_breakdown" in source
        assert "opportunity_components" in source
        assert "historical_evidence_actionable" in source
        assert "profile_rr_ok" in source


def test_ai_review_score_scale_is_consistent_across_breakdown_and_opportunity() -> None:
    from services.opportunity_engine import score_opportunity
    from services.trading_intelligence import _score_breakdown

    signal = {
        "asset": "EURUSD",
        "score": 85.0,
        "ai_review_score": 8.5,
        "ml_probability": 0.60,
        "historical_win_rate": 60.0,
        "asset_health_score": 70.0,
        "rr_ratio": 2.0,
        "time_to_target_score": 75.0,
        "mtf_alignment_score": 80.0,
    }
    breakdown = _score_breakdown(signal)
    opportunity = score_opportunity(signal)

    assert breakdown["ai"] == pytest.approx(85.0)
    assert opportunity.components["ai"] == pytest.approx((85.0 * 0.7) + (60.0 * 0.3))
