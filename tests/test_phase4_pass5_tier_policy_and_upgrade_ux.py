from __future__ import annotations

import pytest

from core.tier_constants import (
    TIER_DAILY_LIMITS,
    TIER_FEATURES,
    TIER_RANK,
    TIER_SCORE_THRESHOLDS,
    TIER_SIGNAL_DEPTH,
)
from core.tier_policy import (
    BUTTON_FEATURE,
    COMMAND_MINIMUM_TIER,
    NON_BYPASSABLE_SAFETY_GATES,
    POLICY_VERSION,
    TIER_ORDER,
    evaluate_button_access,
    evaluate_command_access,
    evaluate_feature_access,
    get_entitlements,
    tier_rank,
)
from services.tier_policy import get_tier_capabilities
from services.upgrade_intents import build_upgrade_intent_event
from signalrank_telegram.command_access import COMMAND_TIERS, check_command_access
from signalrank_telegram.formatter import format_signal_free_new
from signalrank_telegram.tier_delivery import TierDeliveryManager
from signalrank_telegram.tier_gated_formatter import format_tiered_signal


EXPECTED_MATRIX = {
    "FREE": (0, False, 3, 80.0, 10, 1, 7),
    "PREMIUM": (1, True, 15, 80.0, 0, 2, 30),
    "VIP": (2, True, 30, 80.0, 0, 3, 365),
    "PROFESSIONAL": (3, True, 100, 75.0, 0, 3, 1825),
    "INSTITUTIONAL": (4, True, 1000, 0.0, 0, 3, 3650),
    "ADMIN": (5, False, 100, 0.0, 0, 3, 3650),
    "OWNER": (6, False, 100, 0.0, 0, 3, 3650),
}


@pytest.mark.parametrize("tier", [item.value for item in TIER_ORDER])
def test_canonical_tier_matrix_and_legacy_adapters_match(tier: str) -> None:
    rank, purchasable, quota, score, delay, depth, history = EXPECTED_MATRIX[tier]
    policy = get_entitlements(tier)
    caps = get_tier_capabilities(tier)
    key = tier.lower()

    assert tier_rank(tier) == rank
    assert policy.purchasable is purchasable
    assert policy.daily_signal_limit == quota
    assert policy.minimum_signal_score == score
    assert policy.delivery_delay_minutes == delay
    assert policy.max_tp_levels == depth
    assert policy.history_days == history

    assert TIER_RANK[key] == rank
    assert TIER_DAILY_LIMITS[key] == float(quota)
    assert TIER_SCORE_THRESHOLDS[key] == score
    assert TIER_SIGNAL_DEPTH[key]["max_tp_level"] == depth
    assert TIER_FEATURES[key] == set(policy.features)
    assert caps.daily_limit == quota
    assert caps.delivery_delay_minutes == delay
    assert caps.max_tp_levels == depth
    assert caps.auto_trading is False
    assert caps.execution_eligible is policy.has("execution_preflight")


def test_every_registered_command_uses_the_canonical_matrix() -> None:
    assert COMMAND_TIERS == {
        command: required.value
        for command, required in COMMAND_MINIMUM_TIER.items()
    }
    for command, required in COMMAND_MINIMUM_TIER.items():
        for tier in TIER_ORDER:
            expected = tier_rank(tier) >= tier_rank(required)
            decision = evaluate_command_access(command, tier)
            allowed, reason = check_command_access(command, tier.value)
            assert decision.allowed is expected, (command, tier, required)
            assert allowed is expected, (command, tier, required, reason)


def test_every_registered_button_uses_the_canonical_feature_matrix() -> None:
    for action, feature in BUTTON_FEATURE.items():
        for tier in TIER_ORDER:
            expected = get_entitlements(tier).has(feature)
            decision = evaluate_button_access(f"{action}_payload", tier)
            assert decision.feature == feature
            assert decision.allowed is expected, (action, feature, tier)


@pytest.mark.parametrize("tier", [item.value for item in TIER_ORDER])
def test_no_tier_can_bypass_any_safety_gate(tier: str) -> None:
    checks = {name: False for name in NON_BYPASSABLE_SAFETY_GATES}
    decision = evaluate_feature_access(tier, "basic_signals", safety_checks=checks)
    assert decision.allowed is False
    assert decision.code == "SAFETY_BLOCKED"
    assert set(decision.safety_failures) == NON_BYPASSABLE_SAFETY_GATES
    assert "Upgrading cannot bypass" in decision.reason


def test_upgrade_reason_and_event_are_value_led_and_auditable() -> None:
    decision = evaluate_button_access("monitor_signal_abc123", "FREE")
    assert decision.allowed is False
    assert decision.code == "TIER_LOCKED"
    assert decision.required_tier.value == "PREMIUM"
    assert "lifecycle updates" in decision.reason
    assert "identical on every tier" in decision.reason
    assert "no outcome is guaranteed" in decision.reason

    event = build_upgrade_intent_event(
        decision,
        action="monitor_signal",
        source="telegram_button",
    )
    assert event == {
        "event": "upgrade_intent",
        "action": "monitor_signal",
        "source": "telegram_button",
        "feature": "lifecycle_updates",
        "current_tier": "FREE",
        "required_tier": "PREMIUM",
        "decision_code": "TIER_LOCKED",
        "policy_version": POLICY_VERSION,
    }


def _callback_data(markup) -> set[str]:
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_signal_formatting_obeys_depth_and_execution_preflight_contract() -> None:
    signal = {
        "asset": "TESTUSDT",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 90.0,
        "take_profit": [110.0, 120.0, 130.0],
        "score": 88.0,
        "signal_id": "policy-123",
    }

    free_text, free_markup = format_tiered_signal(signal, "FREE")
    premium_text, premium_markup = format_tiered_signal(signal, "PREMIUM")
    vip_text, vip_markup = format_tiered_signal(signal, "VIP")

    assert "Entry:** `100" not in free_text
    assert "Stop Loss:** `90" not in free_text
    assert "Illustrative TP1" in free_text
    assert "TP2: `120" in premium_text
    assert "TP3: `130" not in premium_text
    assert "TP3" in premium_text and "VIP MANAGEMENT LADDER" in premium_text
    assert "TP3: `130" in vip_text
    assert not any(item.startswith("mt5_trade_") for item in _callback_data(free_markup))
    assert not any(item.startswith("mt5_trade_") for item in _callback_data(premium_markup))
    assert "mt5_trade_policy-123" in _callback_data(vip_markup)

    primary_free = format_signal_free_new(signal)
    assert "Entry + Stop Loss" in primary_free
    assert "100.0" not in primary_free
    assert "90.0" not in primary_free
    assert "Educational preview only" in primary_free
    assert "no guaranteed returns" in primary_free


def test_delivery_projection_and_outcomes_follow_canonical_depth() -> None:
    manager = TierDeliveryManager()
    for tier in TIER_ORDER:
        policy = get_entitlements(tier)
        projection = manager.get_tier_features(tier.value)
        assert projection["signals_per_day"] == str(policy.daily_signal_limit)
        assert projection["min_score"] == int(policy.minimum_signal_score)
        assert projection["multiple_tps"] is (policy.max_tp_levels > 1)

    assert manager.format_outcome_for_tier("signal-1", "tp2", 2, "FREE") is None
    assert manager.format_outcome_for_tier("signal-1", "tp2", 2, "PREMIUM")
    assert manager.format_outcome_for_tier("signal-1", "tp3", 3, "PREMIUM") is None
    assert manager.format_outcome_for_tier("signal-1", "tp3", 3, "VIP")
