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
            score=89.0,
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


def test_production_quality_guard_rejects_low_confluence_when_present(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="AUDUSD",
            direction="short",
            entry=0.69137,
            stop_loss=0.69275,
            take_profit=0.68700,
            score=96.6,
            ml_probability=0.733,
            adx=30.0,
            mtf_4h_trend=-1.0,
            mtf_1d_trend=-1.0,
            confluence_percent=33.0,
        )
    )

    assert not ok
    assert "quality_confluence" in reason


def test_production_quality_guard_uses_trade_profile_rr_for_atr_day_signals(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)
    monkeypatch.delenv("QUALITY_MIN_RR_CRYPTO", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="AVAXUSDT",
            timeframe="5m",
            entry=20.0,
            stop_loss=19.5,
            take_profit=[20.615, 21.0, 21.5],
            score=97.5,
            ml_probability=0.80,
            adx=30.0,
            trade_profile="day",
            target_model="atr_profile",
            rr_ratio=1.23,
            rr_estimate=1.23,
        )
    )

    assert ok
    assert reason == ""


def test_production_quality_guard_env_can_keep_profile_rr_strict(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)
    monkeypatch.setenv("QUALITY_MIN_RR_CRYPTO", "2.0")

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="AVAXUSDT",
            timeframe="5m",
            entry=20.0,
            stop_loss=19.5,
            take_profit=[20.615, 21.0, 21.5],
            score=97.5,
            ml_probability=0.80,
            adx=30.0,
            trade_profile="day",
            target_model="atr_profile",
            rr_ratio=1.23,
            rr_estimate=1.23,
        )
    )

    assert not ok
    assert "quality_rr 1.23 < 2.00" in reason


def test_production_quality_guard_allows_bounded_paper_ml_recovery(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)
    monkeypatch.delenv("QUALITY_MIN_SCORE_FX", raising=False)
    monkeypatch.setenv("PREMIUM_SCORE_THRESHOLD", "75")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_MIN_SCORE", "82")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_RAW_FLOOR", "0.50")

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="EURUSD",
            direction="long",
            entry=1.1000,
            stop_loss=1.0950,
            take_profit=1.1110,
            score=76.0,
            _preview_score=85.0,
            ml_recovery_structural_score=85.0,
            ml_recovery_mode=True,
            ml_probability=0.60,
            ml_probability_raw=0.58,
            ml_recovery_champion_raw_probability=0.58,
            ml_recovery_certified_threshold=0.83,
            confluence_score=75.0,
            adx=30.0,
            mtf_4h_trend=1.0,
            mtf_1d_trend=1.0,
        )
    )

    assert ok is True
    assert reason == ""


def test_normal_fx_signal_still_uses_normal_ml_quality_floor(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)
    monkeypatch.delenv("QUALITY_MIN_SCORE_FX", raising=False)

    ok, reason = _production_quality_gate(
        _base_signal(
            asset="EURUSD",
            direction="long",
            entry=1.1000,
            stop_loss=1.0950,
            take_profit=1.1110,
            score=90.0,
            ml_probability=0.60,
            confluence_score=75.0,
            adx=30.0,
            mtf_4h_trend=1.0,
            mtf_1d_trend=1.0,
        )
    )

    assert ok is False
    assert "quality_ml" in reason
