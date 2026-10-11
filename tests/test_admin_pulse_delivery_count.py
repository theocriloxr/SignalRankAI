from pathlib import Path


def test_admin_pulse_counts_only_confirmed_deliveries():
    source = (Path(__file__).resolve().parents[1] / "engine" / "admin_pulse.py").read_text(encoding="utf-8")

    assert "FROM signal_deliveries WHERE delivered_at >= :since AND sent_ok IS TRUE" in source


def test_admin_pulse_explains_ml_signal_drought(monkeypatch):
    from engine.admin_pulse import _cycle_signal_drought_summary

    monkeypatch.setenv("ML_STARVATION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_MAX_SIGNALS_PER_CYCLE", "1")
    lines = _cycle_signal_drought_summary({
        "delivered": 0,
        "latest_cycle": {
            "max_score_pre_threshold": 90.42,
            "pipeline_stats": {
                "strategy_signals": 80,
                "strict_candidates": 15,
                "ml_passed": 0,
                "ml_raw_probability_max": 0.588154,
                "ml_calibrated_probability_max": 0.645346,
                "ml_threshold_raw": 0.78,
                "ml_forward_observations_disabled": 15,
                "ml_forward_observations_failed": 1,
            },
        },
    })
    joined = "\n".join(lines)
    assert "80 strategy ideas -> 15 strict candidates -> 0 ML passes" in joined
    assert "raw max 58.8%" in joined
    assert "certified cutoff 78.0%" in joined
    assert "best pre-threshold score: 90.42" in joined
    assert "PAPER-ONLY" in joined
    assert "Telegram is waiting for an admitted signal" in joined
    assert "recording is disabled on the engine" in joined
    assert "submission failed" in joined
