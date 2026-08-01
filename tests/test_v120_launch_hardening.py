from __future__ import annotations

import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_version_and_migration_head():
    assert 'default="1.2.1"' in source("core/version.py")
    migration = source("db/migrations/versions/0027_launch_paper_trading.py")
    assert 'revision = "0027_launch_paper_trading"' in migration
    assert 'down_revision = "0026_adaptive_operational_hotfix"' in migration
    assert '"paper_accounts"' in migration
    assert '"paper_positions"' in migration
    assert '"paper_ledger_entries"' in migration


def test_rich_cards_require_explicit_canary_mode(monkeypatch):
    from signalrank_telegram.rich_messages import rich_messages_enabled

    monkeypatch.setenv("TELEGRAM_RICH_MESSAGES_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_RICH_MESSAGES_CERTIFIED", "1")
    monkeypatch.setenv("TELEGRAM_RICH_MESSAGES_MODE", "off")
    assert rich_messages_enabled() is False
    monkeypatch.setenv("TELEGRAM_RICH_MESSAGES_MODE", "canary")
    assert rich_messages_enabled() is True


def test_execution_codes_are_never_primary_user_message():
    from signalrank_telegram.execution_messages import execution_failure_html

    text = execution_failure_html("broker_account_not_ready", asset="XAUTUSDT")
    assert "connect" in text.lower()
    assert "/mt5_link" in text
    assert "Trade not executed" in text
    assert text.index("Your broker account") < text.index("broker_account_not_ready")


def test_command_catalog_hides_admin_from_free_and_has_clear_descriptions():
    from signalrank_telegram.command_catalog import visible_commands

    free = visible_commands("FREE")
    free_names = {item.name for item in free}
    assert "admin" not in free_names
    assert "adaptive_promote" not in free_names
    assert "paper_settings" in free_names
    assert all(item.description and item.description.lower() != "command" for item in free)
    admin_names = {item.name for item in visible_commands("ADMIN")}
    assert "admin" in admin_names
    assert "adaptive_promote" in admin_names


def test_canonical_policy_protects_admin_commands():
    from core.tier_policy import evaluate_command_access

    assert not evaluate_command_access("delivery_eligibility", "FREE").allowed
    assert not evaluate_command_access("adaptive_promote", "VIP").allowed
    assert evaluate_command_access("adaptive_promote", "ADMIN").allowed


def test_paper_target_parser_and_accounting_contract():
    from core.paper_trading_service import parse_targets

    assert parse_targets('[101, 102, 103]') == [101.0, 102.0, 103.0]
    assert parse_targets({"tp1": 101, "tp2": 102}) == [101.0, 102.0]
    service = source("core/paper_trading_service.py")
    assert "CONFIRMED_DELIVERY_STATES" in service
    assert "telegram_chat_id.is_not(None)" in service
    assert "telegram_message_id.is_not(None)" in service
    assert 'position.unrealized_pnl = gross' in service
    assert 'result_status = "deferred"' in service
    assert "signal_entry_fallback" not in service


def test_about_counts_canonical_delivery_states_and_no_static_zero_path():
    commands = source("signalrank_telegram/commands.py")
    assert 'Signals confirmed delivered to you: <b>{delivered}</b>' in commands
    assert 'func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"])' in commands
    assert "from core.version import APP_VERSION" in commands


def test_simulation_has_no_invented_win_rate_fallback():
    commands = source("signalrank_telegram/commands.py")
    simulate = commands[commands.index("async def simulate_command"):]
    assert "Simulation evidence is not sufficient yet" in simulate
    assert "55%" not in simulate
    assert "avg_win_r=1.8" not in simulate
    assert "No default win rate or invented reward assumption was used" in simulate


def test_price_batch_ignores_individual_failures(monkeypatch):
    import engine.price_fetcher as price_fetcher

    async def fake(asset: str):
        if asset == "BAD":
            raise RuntimeError("provider failed")
        return 123.45

    monkeypatch.setattr(price_fetcher, "get_live_price", fake)
    result = asyncio.run(price_fetcher.get_live_price_batch(["GOOD", "BAD"], max_concurrent=2))
    assert result == {"GOOD": 123.45}


def test_launch_catalog_commands_are_registered():
    import re
    from signalrank_telegram.command_catalog import COMMANDS

    bot = source("signalrank_telegram/bot.py")
    registered = set(re.findall(r'CommandHandler\(\s*["\']([^"\']+)', bot))
    missing = [spec.name for spec in COMMANDS if spec.name not in registered]
    assert missing == []
    assert "delete_my_commands" in bot
    assert "BotCommandScopeAllPrivateChats" in bot
    audit_pos = bot.rfind("def _audit_handler(command_name: str, handler):")
    guard_pos = bot.index("Canonical server-side command authorization", audit_pos)
    registration_pos = bot.index('application.add_handler(CommandHandler("start"')
    assert audit_pos < guard_pos < registration_pos
