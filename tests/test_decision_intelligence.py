import pytest

from services.decision_intelligence import (
    build_decision_record,
    persist_decision_record,
    validate_decision_record,
)


def test_build_decision_record_contains_required_audit_sections():
    record = build_decision_record(
        {
            "signal_id": "sig-1",
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "score": 82,
            "ml_probability": 0.71,
            "strategy_name": "EMA Trend",
            "rr_ratio": 2.4,
            "regime": "trend",
        },
        news_assessment={"confidence_adjustment": -0.1, "signal_action": "delay"},
        votes_against=[{"gate": "news", "reason": "volatility elevated"}],
        shadow_prediction={"available": True, "agreement": 0.82},
    )

    validation = validate_decision_record(record)

    assert validation["ok"] is True
    assert record["asset"] == "BTCUSDT"
    assert record["strategy_votes"][0]["strategy"] == "EMA Trend"
    assert record["confidence_calibration"]["calibrated_confidence"] == pytest.approx(0.61)
    assert record["shadow_agreement"]["agreement"] == 0.82


@pytest.mark.asyncio
async def test_persist_decision_record_delegates_to_repository(monkeypatch):
    captured = {}

    async def fake_persist_decision_log(**kwargs):
        captured.update(kwargs)
        return 42

    monkeypatch.setattr("db.repository.persist_decision_log", fake_persist_decision_log)

    record = build_decision_record(
        {
            "signal_id": "sig-2",
            "asset": "ETHUSDT",
            "timeframe": "15m",
            "direction": "short",
            "decision": "rejected",
        },
        votes_against=[{"gate": "ml", "reason": "below threshold"}],
    )

    row_id = await persist_decision_record(record)

    assert row_id == 42
    assert captured["signal_id"] == "sig-2"
    assert captured["decision"] == "rejected"
    assert captured["meta"]["validation"]["ok"] is True
