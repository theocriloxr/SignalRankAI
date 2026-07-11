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


def test_same_asset_cooldown_is_asset_wide_and_at_least_12h():
    source = (Path(__file__).resolve().parents[1] / "db" / "pg_features.py").read_text(encoding="utf-8")
    asset_gate = source.split("# Same-asset exposure gate:", 1)[1].split("if market_cutoff is not None:", 1)[0]

    assert "Signal.asset == sig.asset" in asset_gate
    assert "Signal.direction == sig.direction" not in asset_gate
    assert "asset_cooldown_hours = max(12.0" in source
    assert "if should_block_asset:" in asset_gate


def test_inflight_delivery_reservation_blocks_duplicate_send_attempts():
    source = (Path(__file__).resolve().parents[1] / "db" / "pg_features.py").read_text(encoding="utf-8")

    assert "DELIVERY_INFLIGHT_RETRY_SECONDS" in source
    assert "in-flight delivery reservation blocked" in source
    assert "last_attempt_at" in source
