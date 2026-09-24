from __future__ import annotations

from signalrank_telegram.tier_signal_formatter import format_premium_signal, format_vip_signal


def _signal() -> dict:
    return {
        "asset": "EURUSD",
        "direction": "long",
        "entry": 1.1,
        "stop_loss": 1.095,
        "take_profit": [1.105, 1.11, 1.115],
        "score": 82,
        "timeframe": "1h",
        "candle_evidence": {
            "evidence_score_pct": 80,
            "body_ratio": 0.55,
            "upper_wick_ratio": 0.10,
            "lower_wick_ratio": 0.35,
            "body_classification": "moderate_bullish",
            "close_control": "buyers",
            "rejection": "lower_price_rejection",
            "market_context": "at_support",
            "relative_volume": 1.4,
            "confirmation": "confirmed",
        },
    }


def test_premium_output_explains_body_wicks_context_and_confirmation() -> None:
    output = format_premium_signal(_signal())
    assert "Price Action Evidence: 80/100" in output
    assert "Body: moderate bullish" in output
    assert "Wicks: upper 10% / lower 35%" in output
    assert "Context: at support" in output
    assert "Confirmation: confirmed" in output
    assert "evidence, not proof" in output


def test_vip_output_adds_volume_context() -> None:
    output = format_vip_signal(_signal())
    assert "Volume: 1.40x baseline" in output
    assert "Next candle: confirmed" in output
