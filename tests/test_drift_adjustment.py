from unittest.mock import patch


def test_drift_confidence_adjustment_reduces_score():
    from engine.loop import _apply_drift_confidence_adjustment

    with patch("engine.loop.state.get_sync", side_effect=["penalize", "0.6"]):
        adjusted, meta = _apply_drift_confidence_adjustment(0.8)

    assert adjusted is not None
    assert adjusted < 0.8
    assert meta["mode"] == "penalize"


def test_drift_confidence_adjustment_ignored_when_normal():
    from engine.loop import _apply_drift_confidence_adjustment

    with patch("engine.loop.state.get_sync", side_effect=["normal", "0"]):
        adjusted, meta = _apply_drift_confidence_adjustment(0.8)

    assert adjusted == 0.8
    assert meta == {}