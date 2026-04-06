from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_realtime_outcome_delivery_has_tp_tier_gate_rules() -> None:
    tracker = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert 'if tier_at_send == "free":' in tracker
    assert "can_receive_tp = tp_level_num == 1" in tracker
    assert 'elif tier_at_send == "premium":' in tracker
    assert "can_receive_tp = tp_level_num in {1, 2}" in tracker
    assert 'elif tier_at_send in {"vip", "admin", "owner"}:' in tracker
    assert "can_receive_tp = tp_level_num in {1, 2, 3}" in tracker
