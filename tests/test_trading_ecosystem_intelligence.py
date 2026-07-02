from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _candles(start: float, step: float, n: int = 80):
    return [
        {"open": start + i * step, "high": start + i * step + 0.4, "low": start + i * step - 0.4, "close": start + i * step}
        for i in range(n)
    ]


def test_asset_registry_classifies_indices_and_builds_provider_routes():
    from services.asset_registry import build_asset_profile, classify_asset, discover_asset_universe

    assert classify_asset("NAS100") == "index"
    assert classify_asset("US500") == "index"
    assert classify_asset("EURUSD") == "fx"
    profile = build_asset_profile("US500")

    assert profile.asset_class == "index"
    assert "day" in profile.recommended_profiles
    assert profile.broker_symbols["mt5"]
    assert discover_asset_universe(limit_per_class=1)


def test_mtf_consensus_marks_ltf_sell_inside_htf_buy_as_pullback():
    from services.mtf_consensus import analyze_mtf_consensus

    signal = {"asset": "EURUSD", "timeframe": "5m", "direction": "sell"}
    market_data = {
        "5m": {"candles": _candles(100, -0.05)},
        "15m": {"candles": _candles(100, -0.03)},
        "1h": {"candles": _candles(100, 0.05)},
        "4h": {"candles": _candles(100, 0.08)},
    }
    consensus = analyze_mtf_consensus(signal, market_data)

    assert consensus.higher_timeframe_bias == "bullish"
    assert consensus.trade_type in {"Counter-trend pullback", "Mixed-timeframe conflict"}
    assert consensus.confidence_modifier < 1.0
    assert "1h" in consensus.conflicting_timeframes or "4h" in consensus.conflicting_timeframes


def test_market_intelligence_scores_session_and_tradability():
    from services.market_intelligence import evaluate_market

    market = evaluate_market("BTCUSDT", signal={"strategy_name": "EMA Trend"}, candles=_candles(100, 1.0))

    assert market.asset_class == "crypto"
    assert market.market_open is True
    assert market.asset_health_score > 0
    assert market.scan_priority > 0


def test_user_preferences_and_tier_policy_gate_delivery():
    from services.tier_policy import apply_tier_visibility, get_tier_capabilities, tier_allows_signal
    from services.user_intelligence import UserTradingPreferences, signal_matches_preferences

    free = get_tier_capabilities("free")
    assert free.max_tp_levels == 1
    assert free.delivery_delay_minutes >= 0
    stock_signal = {"asset": "AAPL", "asset_class": "stock", "take_profit": [1, 2, 3]}
    assert tier_allows_signal(stock_signal, "free")[0] is False
    assert apply_tier_visibility(stock_signal, "free")["visible_take_profit"] == [1]

    prefs = UserTradingPreferences(trade_profile="day", risk_profile="conservative", asset_classes=("fx",), sessions=("london",))
    assert signal_matches_preferences({"asset": "EURUSD", "asset_class": "fx", "timeframe": "15m", "market_session": "London"}, prefs)[0]
    assert not signal_matches_preferences({"asset": "BTCUSDT", "asset_class": "crypto", "timeframe": "15m", "market_session": "London"}, prefs)[0]


def test_opportunity_engine_and_mission_control_outputs():
    from services.mission_control import build_mission_snapshot
    from services.opportunity_engine import score_opportunity

    signal = {
        "asset": "XAUUSD",
        "asset_class": "commodity",
        "timeframe": "15m",
        "direction": "long",
        "entry": 3984.5,
        "stop_loss": 3978.0,
        "take_profit": [3992.5, 3996.5, 4002.5],
        "score": 94,
        "ml_probability": 0.81,
        "asset_health_score": 82,
        "time_to_target_score": 88,
        "mtf_alignment_score": 77,
    }
    opportunity = score_opportunity(signal)
    mission = build_mission_snapshot(signal, current_price=3988.5)

    assert opportunity.score > 70
    assert "technical" in opportunity.components
    assert mission.health_score > 0
    assert mission.progress_to_tp1_pct > 0
    assert mission.recommendation


def test_trading_intelligence_enrichment_adds_required_fields():
    from services.trading_intelligence import enrich_signal_intelligence

    signal = {
        "asset": "EURUSD",
        "timeframe": "5m",
        "direction": "sell",
        "entry": 1.10,
        "stop_loss": 1.101,
        "take_profit": [1.099, 1.098],
        "score": 92,
    }
    enriched = enrich_signal_intelligence(
        signal,
        market_data={
            "5m": {"candles": _candles(1.10, -0.0001)},
            "1h": {"candles": _candles(1.10, 0.0001)},
        },
    )

    assert enriched["asset_class"] == "fx"
    assert "trade_type" in enriched
    assert "confidence_breakdown" in enriched
    assert "opportunity_score" in enriched
    assert "trade_health" in enriched


def test_mission_command_and_intelligence_flags_are_registered():
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    access = (ROOT / "signalrank_telegram" / "command_access.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert 'CommandHandler("mission"' in bot
    assert '"mission":             "PREMIUM"' in access
    assert "async def mission_command" in commands
    assert "SIGNAL_INTELLIGENCE_ENGINE_ENABLED=1" in env
