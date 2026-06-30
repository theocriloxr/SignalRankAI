from pathlib import Path


def test_updated_signal_jump_button_uses_url_not_callback():
    source = (Path(__file__).resolve().parents[1] / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    snippet = source.split('InlineKeyboardButton(\n                        "Go to signal"', 1)[1].split(")]]", 1)[0]

    assert "url=_build_signal_message_link" in snippet
    assert "callback_data" not in snippet


def test_tp_notification_formatter_has_asset_and_ref_fallbacks():
    from engine.tier_notifications import TierNotificationManager

    manager = TierNotificationManager()
    msg = manager.format_tp_hit_notification(
        {
            "asset": "ETHUSDT",
            "signal_id": "abcdef123456",
            "direction": "long",
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": [102.0, 104.0, 106.0],
            "timeframe": "1h",
        },
        "vip",
        1,
        2.0,
        102.0,
    )

    assert "ETHUSDT" in msg
    assert "abcdef12" in msg
    assert "None" not in msg
    assert "N/A" not in msg


def test_ai_review_is_visible_for_vip_signals():
    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    msg = format_vip_signal(
        {
            "asset": "EURUSD",
            "direction": "long",
            "score": 92,
            "ml_probability": 0.74,
            "gemini_review_score": 8.7,
            "gemini_review_reason": "macro_trend_confirmed",
            "entry": 1.1,
            "stop_loss": 1.095,
            "take_profit": [1.107, 1.114, 1.121],
            "timeframe": "1h",
            "signal_id": "sig-1234567890",
        }
    )

    assert "AI Review:" in msg
    assert "Gemini 8.7/10" in msg
    assert "macro trend confirmed" in msg


def test_quality_gate_blocks_low_gemini_score_when_present():
    from engine.core import _production_quality_gate

    ok, reason = _production_quality_gate(
        {
            "asset": "EURUSD",
            "direction": "long",
            "timeframe": "1h",
            "score": 96,
            "ml_probability": 0.9,
            "rr_ratio": 2.5,
            "entry": 1.1,
            "stop_loss": 1.095,
            "gemini_review_score": 6.5,
            "adx": 30,
            "mtf_4h_trend": 1,
            "mtf_1d_trend": 1,
        }
    )

    assert ok is False
    assert "quality_gemini" in reason
