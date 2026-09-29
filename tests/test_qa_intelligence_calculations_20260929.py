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
