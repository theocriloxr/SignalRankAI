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
    history = engine.index("get_best_live_performance_context")
    review = engine.index("gemini_ok, gemini_score, gemini_reason", history)
    assert history < review
    block = engine[history:review]
    assert 'sig["historical_sample_size"]' in block
    assert 'sig["historical_evidence_scope"]' in block
    assert 'sig["historical_evidence_fallback_depth"]' in block
    assert 'sig["live_expectancy"]' in block


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


def test_paper_recovery_ultra_failure_is_advisory_but_normal_ultra_failure_stays_hard() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    ultra = engine[
        engine.index("if _env_bool('ULTRA_QUALITY_ENABLED'"):
        engine.index("# ML-driven dynamic risk sizing hint")
    ]
    assert 'if bool(sig.get("ml_recovery_mode"))' in ultra
    assert 'sig["ml_recovery_ultra_advisory"] = ultra_reason' in ultra
    assert "canonical_quality_continues=1" in ultra
    assert '_post_ml_reject(sig, "ultra_quality", sig[\'rejection_reason\'])' in ultra
    assert "continue" in ultra


def test_post_ml_funnel_records_explicit_stage_and_reason() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    assert "post_ml_rejections = Counter()" in engine
    assert 'candidate["post_ml_rejection_stage"] = stage_key' in engine
    assert 'candidate["post_ml_rejection_reason"] = reason_key' in engine
    assert '_post_ml_reject(sig, "production_quality", quality_reason)' in engine
    assert '_post_ml_reject(sig, "canonical_quality", sig["rejection_reason"])' in engine
    assert "post_ml_reasons = Counter(post_ml_rejections)" in engine


def test_ml_recovery_delivery_defaults_to_operator_only(monkeypatch) -> None:
    from signalrank_telegram.tier_delivery import recovery_delivery_allowed

    signal = {"ml_recovery_mode": True, "score": 90}
    monkeypatch.delenv("ML_RECOVERY_DELIVERY_AUDIENCE", raising=False)
    assert recovery_delivery_allowed(signal, "free") is False
    assert recovery_delivery_allowed(signal, "premium") is False
    assert recovery_delivery_allowed(signal, "professional") is False
    assert recovery_delivery_allowed(signal, "institutional") is False
    assert recovery_delivery_allowed(signal, "admin") is True
    assert recovery_delivery_allowed(signal, "owner") is True
    assert recovery_delivery_allowed({"ml_recovery_mode": False}, "free") is True

    monkeypatch.setenv("ML_RECOVERY_DELIVERY_AUDIENCE", "all")
    assert recovery_delivery_allowed(signal, "free") is True


def test_automatic_distribution_includes_every_canonical_tier() -> None:
    root = Path(__file__).resolve().parents[1]
    distribution = (root / "signalrank_telegram" / "signal_distribution.py").read_text(encoding="utf-8")
    bot = (root / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "from core.tier_policy import TIER_ORDER" in distribution
    assert "result = {tier.value.lower(): [] for tier in TIER_ORDER}" in distribution
    assert "'professional': 4" in distribution
    assert "'institutional': 6" in distribution
    assert "return normalize_tier(tier).value.lower()" in bot
    assert "'professional': 100" in bot
    assert "'institutional': 100" in bot
    assert "('premium', 'vip', 'professional', 'institutional', 'admin', 'owner')" in bot


def test_score_breakdown_preserves_real_zero_values() -> None:
    from services.trading_intelligence import _score_breakdown

    breakdown = _score_breakdown(
        {
            "score": 80,
            "volume_score": 0.0,
            "relative_volume": 1.9,
            "historical_win_rate": 0.0,
            "segment_win_rate": 72.0,
            "ai_review_score": 8.0,
        }
    )
    assert breakdown["volume"] == 0.0
    assert breakdown["historical"] == 0.0
    assert breakdown["ai"] == 80.0


@pytest.mark.asyncio
async def test_historical_context_prefers_specific_actionable_segment(monkeypatch) -> None:
    import engine.expectancy_gate as expectancy

    calls: list[tuple[str | None, str | None]] = []

    async def fake_context(asset, strategy=None, timeframe=None, lookback_hours=0):
        calls.append((strategy, timeframe))
        if strategy == "breakout" and timeframe == "15m":
            return {"actionable": False, "sample_size": 3, "reason": "insufficient_sample"}
        if strategy == "breakout" and timeframe is None:
            return {
                "actionable": True,
                "sample_size": 18,
                "win_rate": 0.61,
                "avg_r": 0.42,
                "expectancy_r": 0.42,
                "reason": "ok",
            }
        return {"actionable": True, "sample_size": 40, "expectancy_r": 0.20, "reason": "ok"}

    monkeypatch.setattr(expectancy, "get_live_performance_context", fake_context)
    result = await expectancy.get_best_live_performance_context(
        "EURUSD",
        strategy="breakout",
        timeframe="15m",
        lookback_hours=720,
    )

    assert result["actionable"] is True
    assert result["scope"] == "asset_strategy"
    assert result["fallback_depth"] == 1
    assert result["sample_size"] == 18
    assert calls == [("breakout", "15m"), ("breakout", None)]


@pytest.mark.asyncio
async def test_historical_context_returns_largest_nonactionable_sample(monkeypatch) -> None:
    import engine.expectancy_gate as expectancy

    async def fake_context(asset, strategy=None, timeframe=None, lookback_hours=0):
        samples = {
            ("breakout", "15m"): 2,
            ("breakout", None): 5,
            (None, "15m"): 8,
            (None, None): 7,
        }
        return {
            "actionable": False,
            "sample_size": samples[(strategy, timeframe)],
            "reason": "insufficient_sample",
        }

    monkeypatch.setattr(expectancy, "get_live_performance_context", fake_context)
    result = await expectancy.get_best_live_performance_context(
        "EURUSD",
        strategy="breakout",
        timeframe="15m",
    )

    assert result["actionable"] is False
    assert result["scope"] == "asset_timeframe"
    assert result["sample_size"] == 8


def test_engine_uses_hierarchical_history_before_ai_review() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    history = engine.index("get_best_live_performance_context")
    review = engine.index("gemini_ok, gemini_score, gemini_reason", history)
    block = engine[history:review]
    assert "strategy_name" in block
    assert "timeframe" in block
    assert 'sig["historical_evidence_scope"]' in block
    assert 'sig["historical_evidence_fallback_depth"]' in block


def test_ai_context_exposes_historical_fallback_depth() -> None:
    root = Path(__file__).resolve().parents[1]
    openai = (root / "services" / "openai_ai.py").read_text(encoding="utf-8")
    gemini = (root / "services" / "gemini_ml.py").read_text(encoding="utf-8")
    assert '"historical_evidence_fallback_depth"' in openai
    assert '"historical_evidence_fallback_depth"' in gemini


def test_instrument_catalogue_persistence_batches_database_round_trips() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "db" / "ecosystem_bootstrap.py").read_text(encoding="utf-8")
    block = source[
        source.index("async def persist_instrument_registry") :
        source.index("async def record_discovery_run")
    ]
    assert "instrument_params: list[dict[str, Any]] = []" in block
    assert "certification_params: list[dict[str, Any]] = []" in block
    assert "mapping_params: list[dict[str, Any]] = []" in block
    assert '), instrument_params)' in block
    assert '), certification_params)' in block
    assert '), mapping_params)' in block
    assert block.count("await session.execute(") == 3
    first_execute = block.index("await session.execute(")
    instrument_loop = block.index("for instrument in registry.all():")
    assert first_execute > instrument_loop


def test_ultra_quality_prefers_numeric_adx_over_strength_label(monkeypatch) -> None:
    from engine.ultra_quality_filter import UltraQualityFilter

    filt = UltraQualityFilter()
    signal = {
        "asset": "EURUSD",
        "direction": "long",
        "score": 90.0,
        "confidence": 0.9,
        "entry": 100.0,
        "close_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": [106.0],
        "regime": "TRENDING",
        "adx": 30.0,
        "adx_trend": "weak",
        "session": "LONDON",
        "trend_ema": 1.0,
        "trend_sma": 1.0,
        "rsi": 60.0,
        "macd_trend": 1.0,
        "volume_ratio": 2.0,
        "nearest_support": 99.0,
        "nearest_resistance": 108.0,
        "volatility": 0.05,
        "atr": 2.0,
        "ema_50": 100.0,
        "htf_bias_aligned": True,
    }
    approved, reason, _ = filt.apply_ultra_filter(signal)
    assert approved is True, reason
    assert "ADX 0.0" not in reason


def test_engine_repairs_missing_atr_before_quality_filters() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "engine" / "core.py").read_text(encoding="utf-8")
    marker = source.index("# Repair a missing ATR from the same point-in-time OHLC")
    filters = source.index("advanced_filters.run_all_filters", marker)
    ultra = source.index("ultra_quality.apply_ultra_filter", filters)
    block = source[marker:filters]
    assert "_canonical_atr = sum(_trs) / len(_trs)" in block
    assert "sig['atr'] = _canonical_atr" in block
    assert "sig['atr_rel'] = _canonical_atr / _close_for_atr" in block
    assert "'adx': _safe_float(sig.get('adx'), 30.0)" in block
    assert marker < filters < ultra


def test_catalogue_symbols_do_not_invent_usd_suffixes() -> None:
    from types import SimpleNamespace
    from db.ecosystem_bootstrap import _catalogue_symbols

    def instrument(asset_class: str, base: str, quote: str, provider_symbol: str):
        return SimpleNamespace(
            id=SimpleNamespace(
                asset_class=SimpleNamespace(value=asset_class),
                base=base,
                quote=quote,
            ),
            provider_symbol=provider_symbol,
        )

    assert _catalogue_symbols(instrument("equity", "GOOGL", "USD", "GOOGL")) == ("GOOGL", "GOOGL")
    assert _catalogue_symbols(instrument("index", "SPX500", "USD", "SPX500")) == ("US500", "US500")
    assert _catalogue_symbols(instrument("commodity", "BRENT", "USD", "BRENT")) == ("BRENT", "BRENT")
    assert _catalogue_symbols(instrument("commodity", "XAU", "USD", "XAUUSD")) == ("XAUUSD", "XAU/USD")
    assert _catalogue_symbols(instrument("forex", "EUR", "USD", "EURUSD")) == ("EURUSD", "EUR/USD")
    assert _catalogue_symbols(instrument("crypto", "BTC", "USDT", "BTCUSDT")) == ("BTCUSDT", "BTC/USDT")


@pytest.mark.asyncio
async def test_historical_context_exposes_wilson_uncertainty(monkeypatch) -> None:
    import engine.expectancy_gate as expectancy

    class Result:
        def first(self):
            return (100, 70, 30, 0.55, 1.4, -0.85, 98.0, -25.5)

    class Session:
        async def execute(self, query):
            return Result()
        async def rollback(self):
            return None

    class Ctx:
        async def __aenter__(self):
            return Session()
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(expectancy, "get_session", lambda **kwargs: Ctx())
    expectancy.clear_expectancy_cache()
    result = await expectancy.get_live_performance_context(
        "EURUSD",
        strategy="breakout",
        timeframe="15m",
        lookback_hours=720,
    )

    assert result["decisive_samples"] == 100
    assert result["win_rate"] == pytest.approx(0.70)
    assert result["win_rate_lower_95"] == pytest.approx(0.60415, rel=1e-3)
    assert result["win_rate_upper_95"] == pytest.approx(0.78105, rel=1e-3)
    assert result["win_rate_lower_95"] < result["win_rate"] < result["win_rate_upper_95"]


def test_opportunity_and_breakdown_prefer_historical_lower_bound() -> None:
    from services.opportunity_engine import score_opportunity
    from services.trading_intelligence import _score_breakdown

    signal = {
        "asset": "EURUSD",
        "score": 90,
        "ml_probability": 0.9,
        "historical_win_rate": 82.0,
        "historical_win_rate_lower_95": 61.0,
        "asset_health_score": 80,
        "rr_ratio": 2.0,
        "time_to_target_score": 80,
        "mtf_alignment_score": 80,
    }
    opportunity = score_opportunity(signal)
    breakdown = _score_breakdown(signal)
    assert opportunity.components["historical"] == pytest.approx(61.0)
    assert breakdown["historical"] == pytest.approx(61.0)


def test_ai_context_includes_historical_uncertainty_bounds() -> None:
    root = Path(__file__).resolve().parents[1]
    openai = (root / "services" / "openai_ai.py").read_text(encoding="utf-8")
    gemini = (root / "services" / "gemini_ml.py").read_text(encoding="utf-8")
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    for source in (openai, gemini):
        assert "historical_win_rate_lower_95" in source
        assert "historical_win_rate_upper_95" in source
        assert "historical_decisive_samples" in source
    assert 'sig["historical_win_rate_lower_95"]' in engine
    assert 'sig["historical_win_rate_upper_95"]' in engine
    assert 'sig["historical_decisive_samples"]' in engine


def test_chop_filter_is_asset_relative_not_absolute_fx_percentages() -> None:
    from engine.advanced_filters import ChopFilter

    filt = ChopFilter()
    # Smooth FX-scale trend: ATR/range are far below the old 1%/2% absolute
    # cutoffs, but directional efficiency is high, so this must not be called chop.
    candles = []
    price = 1.1000
    for idx in range(24):
        close = price + (idx * 0.0002)
        candles.append({
            "open": close - 0.00005,
            "high": close + 0.00012,
            "low": close - 0.00012,
            "close": close,
        })
    blocked, reason = filt.is_choppy(candles, adx=15.0, atr_pct=0.03)
    assert blocked is False
    assert reason == ""


def test_chop_filter_blocks_dimensionless_chop_but_not_range_strategy() -> None:
    from engine.advanced_filters import ChopFilter

    filt = ChopFilter()
    candles = []
    for idx in range(24):
        center = 1.1000 + (0.00008 if idx % 2 else -0.00008)
        candles.append({
            "open": center,
            "high": center + 0.00012,
            "low": center - 0.00012,
            "close": center,
        })
    blocked, reason = filt.is_choppy(candles, adx=12.0, atr_pct=0.02)
    assert blocked is True
    assert "Low directional efficiency" in reason

    blocked_range, range_reason = filt.is_choppy(
        candles,
        adx=12.0,
        atr_pct=0.02,
        range_friendly=True,
    )
    assert blocked_range is False
    assert range_reason == ""


def test_range_strategy_uses_opposite_adx_guard_in_final_quality(monkeypatch) -> None:
    from engine.core import _production_quality_gate

    monkeypatch.setenv("PRODUCTION_QUALITY_GUARD_ENABLED", "1")
    monkeypatch.setenv("QUALITY_MIN_SCORE_FX", "90")
    monkeypatch.setenv("QUALITY_MIN_RR_FX", "2.2")
    monkeypatch.setenv("QUALITY_MIN_ML_PROB_FX", "0.68")
    monkeypatch.setenv("QUALITY_MIN_CONFLUENCE_FX", "50")
    monkeypatch.setenv("QUALITY_MIN_AI_SCORE_FX", "8")
    monkeypatch.setenv("QUALITY_MIN_ADX_FX", "25")
    monkeypatch.setenv("QUALITY_RANGE_MAX_ADX_FX", "28")
    monkeypatch.setenv("QUALITY_FX_REQUIRE_MTF_ALIGNMENT", "0")

    base = {
        "asset": "EURUSD",
        "asset_class": "fx",
        "timeframe": "15m",
        "direction": "long",
        "entry": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": [1.1125],
        "score": 95.0,
        "ml_probability": 0.90,
        "confluence_score": 80.0,
        "ai_review_score": 9.0,
        "strategy_group": "mean_reversion",
        "adx": 14.0,
    }
    ok, reason = _production_quality_gate(dict(base))
    assert ok is True, reason

    trend = dict(base, strategy_group="trend", adx=14.0)
    ok, reason = _production_quality_gate(trend)
    assert ok is False
    assert "quality_adx" in reason

    overtrending_range = dict(base, adx=35.0)
    ok, reason = _production_quality_gate(overtrending_range)
    assert ok is False
    assert "quality_range_adx" in reason


def test_ultra_trend_filter_is_not_globally_applied_to_range_strategies() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    block = engine[
        engine.index("_range_friendly_strategy = False") :
        engine.index("# ML-driven dynamic risk sizing hint")
    ]
    assert 'advanced_filters.is_range_friendly_signal(sig)' in block
    assert '"not_applicable_range_strategy"' in block
    assert "ultra_quality.apply_ultra_filter(sig)" in block
    assert "elif _env_bool('ULTRA_QUALITY_ENABLED', False)" in block


def test_advanced_filter_logs_strategy_and_regime_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")
    marker = engine.index("advanced_filters.run_all_filters")
    block = engine[marker:marker + 5000]
    assert '"strategy_name": sig.get("strategy_name")' in block
    assert '"strategy_group": sig.get("strategy_group")' in block
    assert '"range_friendly_strategy"' in block
    assert '"adx": sig.get("adx")' in block
