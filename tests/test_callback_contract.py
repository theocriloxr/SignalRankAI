from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
COMMANDS_SOURCE = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
TIER_FORMATTER_SOURCE = (
    ROOT / "signalrank_telegram" / "tier_gated_formatter.py"
).read_text(encoding="utf-8")


def test_owner_help_page_has_a_registered_callback_route():
    assert 'callback_data=f"help_page_{allowed_page}"' in COMMANDS_SOURCE
    assert 'pattern=r"^help_page_[1-5]$"' in BOT_SOURCE


def test_owner_help_pages_are_deduplicated():
    assert "return list(dict.fromkeys(pages))" in COMMANDS_SOURCE


def test_upgrade_buttons_use_the_canonical_navigation_route():
    assert 'callback_data="upgrade_menu"' not in TIER_FORMATTER_SOURCE
    assert 'callback_data="nav_upgrade"' in TIER_FORMATTER_SOURCE
    assert "nav_.*" in BOT_SOURCE
