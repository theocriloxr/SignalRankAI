from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_upgrade_message_escapes_markdown_pipe() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert "💎 VIP Monthly — ₦40,000 \\|" in source
    assert "parse_mode=\"MarkdownV2\"" in source


def test_tiers_command_uses_live_pricing_envs() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert 'os.getenv("PREMIUM_MONTHLY_PRICE_NGN", os.getenv("PREMIUM_PRICE_NGN", "24000"))' in source
    assert 'os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000"))' in source


def test_buy_extra_signals_removed_from_command_access() -> None:
    source = (ROOT / "signalrank_telegram" / "command_access.py").read_text(encoding="utf-8")
    assert "buy_extra_signals" not in source
