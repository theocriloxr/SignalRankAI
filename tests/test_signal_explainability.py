from engine.signal_explainability import build_signal_explanation
from engine.webhook_generator import generate_webhook_payload
from signalrank_telegram.tier_signal_formatter import format_vip_signal


def _sample_signal() -> dict:
    return {
        "signal_id": "sig-12345678",
        "asset": "BTCUSDT",
        "direction": "long",
        "timeframe": "1h",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": [{"price": 110.0}, {"price": 120.0}],
        "score": 88.0,
        "technical_reason": "Bullish structure break with volume expansion",
        "confluence_drivers": ["EMA alignment", "Volume spike", "HTF trend aligned"],
        "score_components": {
            "rr_ratio": 2.0,
            "confluence": 82.0,
            "ml_confidence": 0.77,
            "regime_bonus": 1.1,
        },
        "regime": "trending",
        "invalidation": "Below 95.00 invalidates the setup",
        "candle_evidence": {
            "alignment": "supportive",
            "confirmation": "confirmed",
            "summary": "Lower-price rejection at support; evidence, not proof.",
        },
        "candle_reasoning": "Lower-price rejection at support; evidence, not proof.",
        "candle_confirmation": "confirmed",
    }


def test_build_signal_explanation_exposes_reasoning():
    explanation = build_signal_explanation(_sample_signal())

    assert explanation["summary"]
    assert "Bullish structure break" in explanation["summary"]
    assert any("Confluence" in bullet for bullet in explanation["bullets"])
    assert explanation["invalidation"] == "Below 95.00 invalidates the setup"
    assert any("Price action:" in bullet for bullet in explanation["bullets"])
    assert "Next completed candle followed through" in explanation["confirms"]
    assert explanation["candle_evidence"]["alignment"] == "supportive"


def test_vip_formatter_includes_why_block():
    message = format_vip_signal(_sample_signal())

    assert "Why:" in message
    assert "Invalidation:" in message


def test_vip_formatter_never_leaves_why_blank():
    signal = _sample_signal()
    signal.pop("technical_reason")
    signal.pop("confluence_drivers")

    message = format_vip_signal(signal)

    assert "Why:" in message
    why_line = next(line for line in message.splitlines() if line.startswith("Why:"))
    assert why_line.removeprefix("Why:").strip()


def test_webhook_payload_carries_explanation_metadata():
    payload = generate_webhook_payload(_sample_signal())

    assert payload["meta"]["technical_reason"] == "Bullish structure break with volume expansion"
    assert payload["meta"]["explanation"]["summary"]
    assert payload["meta"]["explanation"]["risk_reward"] == 2.0
