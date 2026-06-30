from pathlib import Path


def test_record_signal_delivery_has_central_tier_daily_limit_guard():
    source = (Path(__file__).resolve().parents[1] / "db" / "pg_features.py").read_text(encoding="utf-8")

    assert "TIER_DAILY_LIMITS" in source
    assert "[delivery_limit] blocked" in source
    assert "sent_today >= int(daily_limit)" in source
    assert "SignalDelivery.sent_ok.is_(True)" in source


def test_tier_daily_limits_match_product_defaults():
    from core.tier_constants import TIER_DAILY_LIMITS

    assert TIER_DAILY_LIMITS["free"] == 3.0
    assert TIER_DAILY_LIMITS["premium"] == 15.0
    assert TIER_DAILY_LIMITS["vip"] == 30.0
    assert TIER_DAILY_LIMITS["owner"] == 100.0
    assert TIER_DAILY_LIMITS["admin"] == 100.0


def test_partial_tp_states_do_not_resolve_delivery_dedupe():
    source = (Path(__file__).resolve().parents[1] / "db" / "pg_features.py").read_text(encoding="utf-8")

    resolved_block = source.split("resolved_statuses = {", 1)[1].split("}", 1)[0]
    assert '"tp1"' not in resolved_block
    assert '"tp2"' not in resolved_block
    assert '"tp3"' in resolved_block
    assert '"sl"' in resolved_block
    assert 'os.getenv("DELIVERY_UNRESOLVED_BLOCK_HOURS") or "168"' in source
