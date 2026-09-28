from __future__ import annotations

from pathlib import Path


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _function_slice(source: str, name: str, next_name: str | None = None) -> str:
    start = source.index(f"async def {name}")
    if next_name is None:
        return source[start:]
    end = source.index(f"async def {next_name}", start + 1)
    return source[start:end]


def test_active_mt5_link_copy_never_implies_linking_grants_execution() -> None:
    source = _source("signalrank_telegram/commands.py")
    link = _function_slice(source, "mt5_link_command", "mt5_status_command")
    status = _function_slice(source, "mt5_status_command", "verifybroker_command")

    assert "Linking does not enable trading" in link
    assert "/verifybroker" in link
    assert "Prepare DEMO certification" in link
    assert "keeping execution OFF" in link
    assert "execute instantly" not in link
    assert "Trade on MT5 button" not in link
    assert "one-click MT5 execution" not in link
    assert "AES-256" not in link

    assert "Provider bridge: PROVISIONED" in status
    assert "Execution permission: NOT IMPLIED BY LINKING" in status
    assert "/verifybroker" in status
    assert "trade instantly" not in status
    assert "Execution bridge: READY" not in status


def test_legacy_mt5_helper_cannot_regress_execution_permission_copy() -> None:
    source = _source("signalrank_telegram/mt5_commands.py")
    assert "Linking does not enable trading" in source
    assert "/verifybroker" in source
    assert "execution permission remains OFF" in source
    assert "Ready for signal execution" not in source
    assert "Use Trade buttons on signals to execute" not in source
    assert "one-click MT5 execution" not in source
    assert "AES-256" not in source


def test_live_bot_binds_mt5_commands_from_canonical_commands_module() -> None:
    bot = _source("signalrank_telegram/bot.py")
    assert "from .commands import (" in bot
    assert "mt5_link_command, mt5_status_command, verifybroker_command" in bot
    assert 'CommandHandler("mt5_link"' in bot
    assert 'CommandHandler("mt5_status"' in bot
    assert 'CommandHandler("verifybroker"' in bot
