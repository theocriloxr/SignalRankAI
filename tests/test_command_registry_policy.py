import re
from pathlib import Path

from core.tier_policy import COMMAND_MINIMUM_TIER
from signalrank_telegram.command_catalog import COMMANDS


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
REGISTERED = set(re.findall(r'CommandHandler\(\s*["\x27]([^"\x27]+)', BOT_SOURCE))


def test_every_registered_command_has_an_explicit_access_policy():
    missing = sorted(REGISTERED - set(COMMAND_MINIMUM_TIER))
    assert not missing, f"registered commands defaulting to FREE: {missing}"


def test_every_policy_command_has_a_registered_handler():
    missing = sorted(set(COMMAND_MINIMUM_TIER) - REGISTERED)
    assert not missing, f"policy commands without handlers: {missing}"


def test_every_advertised_command_has_a_handler_and_matching_tier():
    for spec in COMMANDS:
        assert spec.name in REGISTERED, f"/{spec.name} is advertised but not registered"
        assert spec.name in COMMAND_MINIMUM_TIER, f"/{spec.name} has no access policy"
        assert COMMAND_MINIMUM_TIER[spec.name].value == spec.tier, (
            f"/{spec.name}: catalogue={spec.tier} "
            f"policy={COMMAND_MINIMUM_TIER[spec.name].value}"
        )


def test_internal_debug_commands_are_not_public():
    for command in ("profile_debug", "delivery_debug", "signal_debug", "format_debug"):
        assert COMMAND_MINIMUM_TIER[command].value in {"ADMIN", "OWNER"}
