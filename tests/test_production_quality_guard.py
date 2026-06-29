from engine.core import _production_quality_gate


def _base_signal(**overrides):
    signal = {
        "asset": "BTCUSDT",
        "direction": "long",
        "timeframe": "4h",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 112.0,
        "score": 94.0,
        "ml_probability": 0.72,
        "adx": 30.0,
        "mtf_4h_trend": 1.0,
        "mtf_1d_trend": 1.0,
    }
    signal.update(overrides)
    return signal


def test_production_quality_guard_rejects_weak_fx(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="EURUSD",
            score=90.0,
            ml_probability=0.61,
            adx=18.0,
            take_profit=109.0,
        )
    )

    assert not ok
    assert "quality_score" in reason


def test_production_quality_guard_rejects_fx_mtf_mismatch(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="USDJPY",
            direction="long",
            score=98.0,
            ml_probability=0.75,
            adx=32.0,
            mtf_4h_trend=-1.0,
            mtf_1d_trend=1.0,
        )
    )

    assert not ok
    assert "quality_fx_mtf_4h_mismatch" in reason


def test_production_quality_guard_allows_strong_stock(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="AAPL",
            score=91.0,
            ml_probability=0.67,
            adx=24.0,
            take_profit=110.0,
        )
    )

    assert ok
    assert reason == ""
