from datetime import datetime, timedelta, timezone


def test_no_trade_alert_rate_limit_accepts_aware_last_alert_time():
    from engine.signal_context import SignalContext

    ctx = SignalContext()
    should_alert, reason = ctx.should_send_no_trade_alert(
        {"volume_ratio": 0.2, "atr_percent": 1.0, "regime": "ranging", "adx": 10, "spread_pct": 0.1},
        datetime.now(timezone.utc) - timedelta(minutes=30),
    )

    assert should_alert is False
    assert "Too soon" in reason
