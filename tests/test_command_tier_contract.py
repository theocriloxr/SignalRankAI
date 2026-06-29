import unittest
import re
from pathlib import Path

from signalrank_telegram.command_access import COMMAND_TIERS, check_command_access
from signalrank_telegram.commands import _help_page_definitions


class TestTierHelpContract(unittest.TestCase):
    def test_help_surface_commands_exist_in_command_tiers(self):
        pages = _help_page_definitions()
        for page in pages.values():
            for cmd, _desc in page.get("commands", []):
                normalized = str(cmd).strip().lstrip("/").lower()
                self.assertIn(normalized, COMMAND_TIERS)

    def test_help_required_tier_can_access_all_commands_on_page(self):
        pages = _help_page_definitions()
        for page in pages.values():
            required_tier = str(page.get("required_tier") or "FREE").upper()
            for cmd, _desc in page.get("commands", []):
                normalized = str(cmd).strip().lstrip("/").lower()
                can_access, reason = check_command_access(normalized, required_tier)
                self.assertTrue(
                    can_access,
                    msg=f"{required_tier} page lists /{normalized} but access check failed: {reason}",
                )

    def test_hidden_commands_are_not_in_paginated_help_surface(self):
        pages = _help_page_definitions()
        paginated_help_commands = {
            str(cmd).strip().lstrip("/").lower()
            for page in pages.values()
            for cmd, _desc in page.get("commands", [])
        }
        intentionally_hidden = {"unlock", "broadcast", "dev_invalidate", "dev_force_signal"}
        self.assertTrue(intentionally_hidden.isdisjoint(paginated_help_commands))

    def test_help_surface_commands_have_bot_handlers(self):
        pages = _help_page_definitions()
        help_commands = {
            str(cmd).strip().lstrip("/").lower()
            for page in pages.values()
            for cmd, _desc in page.get("commands", [])
        }
        bot_source = (Path(__file__).resolve().parents[1] / "signalrank_telegram" / "bot.py").read_text(
            encoding="utf-8"
        )
        registered = {m.group(1).lower() for m in re.finditer(r'CommandHandler\("([^"]+)"', bot_source)}
        registered.update(
            m.group(1).lower()
            for m in re.finditer(r'_CH\("([^"]+)"', bot_source)
        )
        commands_source = (Path(__file__).resolve().parents[1] / "signalrank_telegram" / "commands.py").read_text(
            encoding="utf-8"
        )
        registered.update(
            m.group(1).lower()
            for m in re.finditer(r'_CH\("([^"]+)"', commands_source)
        )
        missing = sorted(help_commands - registered)
        self.assertFalse(missing, msg=f"/help lists commands without bot handlers: {missing}")


if __name__ == "__main__":
    unittest.main()
