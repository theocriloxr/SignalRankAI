from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_asset_repeat_policy_defaults_to_four_hours_and_reductions_require_audited_flags(monkeypatch):
    from services.asset_repeat_policy import get_asset_repeat_lock_hours

    for name in (
        "ASSET_REPEAT_LOCK_HOURS",
        "DELIVERY_SAME_ASSET_COOLDOWN_HOURS",
        "VIP_ASSET_COOLDOWN_HOURS",
        "PREMIUM_ASSET_COOLDOWN_HOURS",
        "FREE_ASSET_COOLDOWN_HOURS",
        "ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES",
        "ALLOW_ASSET_COOLDOWN_REDUCTION",
    ):
        monkeypatch.delenv(name, raising=False)

    assert get_asset_repeat_lock_hours("free") == 4.0
    assert get_asset_repeat_lock_hours("premium") == 4.0
    assert get_asset_repeat_lock_hours("vip") == 4.0

    monkeypatch.setenv("ASSET_REPEAT_LOCK_HOURS", "6")
    assert get_asset_repeat_lock_hours("free") == 6.0

    monkeypatch.setenv("PREMIUM_ASSET_COOLDOWN_HOURS", "2.5")
    assert get_asset_repeat_lock_hours("premium") == 6.0
    monkeypatch.setenv("ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES", "1")
    assert get_asset_repeat_lock_hours("premium") == 6.0
    monkeypatch.setenv("ALLOW_ASSET_COOLDOWN_REDUCTION", "1")
    assert get_asset_repeat_lock_hours("premium") == 2.5
    assert get_asset_repeat_lock_hours("free") == 6.0


def test_repeat_key_is_direction_agnostic():
    from services.asset_repeat_policy import canonical_delivery_cooldown_key

    assert canonical_delivery_cooldown_key(123, "btcusdt") == "delivery_asset:123:BTCUSDT"


def test_unproven_delivery_does_not_set_redis_lock():
    from signalrank_telegram.delivery_cooldown import set_delivery_cooldown

    with patch("core.redis_state.state") as state:
        assert set_delivery_cooldown(123, "BTCUSDT", "BUY", "free", sent_ok=False) is False
        state.set_sync.assert_not_called()


def test_proven_delivery_sets_direction_agnostic_lock(monkeypatch):
    from signalrank_telegram.delivery_cooldown import set_delivery_cooldown

    monkeypatch.setenv("ASSET_REPEAT_LOCK_HOURS", "4")
    state = MagicMock()
    state.has_redis_sync.return_value = True
    with patch("core.redis_state.state", state):
        assert set_delivery_cooldown(123, "BTCUSDT", "SELL", "free", sent_ok=True) is True

    state.set_sync.assert_called_once_with("delivery_asset:123:BTCUSDT", "1", ex=4 * 3600)


def test_cooldown_reads_legacy_keys_during_migration():
    from signalrank_telegram.delivery_cooldown import check_delivery_cooldown

    state = MagicMock()
    state.has_redis_sync.return_value = True
    state.get_sync.side_effect = [None, "1"]
    with patch("core.redis_state.state", state):
        assert check_delivery_cooldown(123, "BTCUSDT", "BUY") is True
