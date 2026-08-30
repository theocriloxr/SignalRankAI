from core.tier_policy import COMMAND_MINIMUM_TIER, Tier
from signalrank_telegram.command_catalog import COMMANDS


def test_owner_operational_commands_are_tier_mapped() -> None:
    owner_only = {
        "performance_rebuild",
        "performance_audit",
        "outcome_rebuild",
        "outcome_audit",
        "dedup_audit",
        "notification_audit",
        "paper_audit",
        "queue_status",
        "queue_replay",
        "dead_letter_status",
        "dead_letter_replay",
        "ledger_audit",
        "payment_reconcile",
        "release_status",
        "kill_switch",
    }
    for name in owner_only:
        assert COMMAND_MINIMUM_TIER.get(name) == Tier.OWNER


def test_system_health_is_admin_mapped() -> None:
    assert COMMAND_MINIMUM_TIER.get("system_health") == Tier.ADMIN


def test_command_catalog_exposes_new_owner_ops_surface() -> None:
    names = {item.name for item in COMMANDS}
    expected = {
        "dedup_audit",
        "notification_audit",
        "paper_audit",
        "queue_status",
        "queue_replay",
        "dead_letter_status",
        "dead_letter_replay",
        "ledger_audit",
        "payment_reconcile",
        "release_status",
        "kill_switch",
        "system_health",
    }
    assert expected.issubset(names)
