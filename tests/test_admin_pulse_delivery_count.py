from pathlib import Path


def test_admin_pulse_counts_only_confirmed_deliveries():
    source = (Path(__file__).resolve().parents[1] / "engine" / "admin_pulse.py").read_text(encoding="utf-8")

    assert "FROM signal_deliveries WHERE delivered_at >= :since AND sent_ok IS TRUE" in source
