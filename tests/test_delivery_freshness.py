from datetime import datetime, timedelta, timezone

import pytest


def _now():
    return datetime(2026, 7, 2, 6, 28, tzinfo=timezone.utc)


def test_five_minute_signal_nearly_five_hours_old_is_rejected(monkeypatch):
    from engine.delivery_freshness import evaluate_signal_age

    monkeypatch.setenv("DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT", "30")
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "created_at": _now() - timedelta(minutes=296),
        "trade_profile": "day",
    }

    result = evaluate_signal_age(signal, now=_now())

    assert result.ok is False
    assert result.reason.startswith("age_exceeded")
    assert result.max_age_minutes == 10.0


def test_opportunity_decay_blocks_late_short_timeframe_signal(monkeypatch):
    from engine.delivery_freshness import evaluate_signal_age

    monkeypatch.setenv("DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT", "30")
    signal = {
        "asset": "EURUSD",
        "timeframe": "5m",
        "created_at": _now() - timedelta(minutes=8),
        "trade_profile": "day",
    }

    result = evaluate_signal_age(signal, now=_now())

    assert result.ok is False
    assert result.reason.startswith("opportunity_decayed")
    assert result.opportunity_remaining_pct == pytest.approx(20.0)


def test_day_signal_with_enough_remaining_opportunity_is_allowed(monkeypatch):
    from engine.delivery_freshness import evaluate_signal_age

    monkeypatch.setenv("DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT", "30")
    signal = {
        "asset": "EURUSD",
        "timeframe": "1h",
        "created_at": _now() - timedelta(minutes=20),
        "trade_profile": "day",
    }

    result = evaluate_signal_age(signal, now=_now())

    assert result.ok is True
    assert result.max_age_minutes == 45.0
    assert result.opportunity_remaining_pct > 50.0


@pytest.mark.asyncio
async def test_delivery_freshness_fails_closed_when_live_price_unavailable(monkeypatch):
    import engine.stale_signal_validator as stale
    from engine.delivery_freshness import validate_delivery_freshness

    async def fake_validate(*args, **kwargs):
        return True, "price_unavailable_skip", None

    monkeypatch.setattr(stale, "validate_signal_freshness", fake_validate)
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": [104.0],
    }

    result = await validate_delivery_freshness(signal)

    assert result.ok is False
    assert result.reason.startswith("live_price_unavailable")


@pytest.mark.asyncio
async def test_delivery_freshness_accepts_fresh_revalidated_signal(monkeypatch):
    import engine.stale_signal_validator as stale
    from engine.delivery_freshness import validate_delivery_freshness

    async def fake_validate(*args, **kwargs):
        return True, "fresh", 100.2

    monkeypatch.setattr(stale, "validate_signal_freshness", fake_validate)
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": [104.0],
    }

    result = await validate_delivery_freshness(signal, cached_live_price=100.2)

    assert result.ok is True
    assert result.live_price == pytest.approx(100.2)
