from pathlib import Path


def test_record_signal_delivery_has_central_tier_daily_limit_guard():
    source = (Path(__file__).resolve().parents[1] / "db" / "pg_features.py").read_text(encoding="utf-8")

    assert "TIER_DAILY_LIMITS" in source
    assert "[delivery_limit] blocked" in source
    assert "sent_today >= int(daily_limit)" in source
