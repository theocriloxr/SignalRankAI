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
            entry=161.923,
            stop_loss=161.599,
            take_profit=162.763,
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
            entry=100.0,
            stop_loss=99.0,
            score=91.0,
            ml_probability=0.67,
            adx=24.0,
            take_profit=102.8,
        )
    )

    assert ok
    assert reason == ""


def test_production_quality_guard_rejects_small_account_unfriendly_crypto_stop(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="AVAXUSDT",
            entry=5.85,
            stop_loss=6.805,
            take_profit=4.20,
            direction="short",
            score=96.0,
            ml_probability=0.78,
            adx=30.0,
        )
    )

    assert not ok
    assert "quality_stop_loss_pct" in reason


def test_production_quality_guard_rejects_roi_chasing_extreme_rr(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="USDJPY",
            entry=161.923,
            stop_loss=161.599,
            take_profit=164.444,
            direction="long",
            score=98.0,
            ml_probability=0.78,
            adx=30.0,
            mtf_4h_trend=1.0,
            mtf_1d_trend=1.0,
        )
    )

    assert not ok
    assert "quality_rr" in reason
