from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_telegram_never_collects_broker_passwords() -> None:
    commands = _source("signalrank_telegram/commands.py")
    compat = _source("signalrank_telegram/mt5_commands.py")
    combined = commands + "\n" + compat

    forbidden = (
        "/mt5_link <login> <password> <server>",
        "<Account Number> <Password> <Server Name>",
        "MyP@ssw0rd",
        "MyPass123",
        'context.user_data["mt5_password"]',
        "Enter your <b>MT5 password</b>",
        "execute trades instantly",
        "Check your login/password/server",
    )
    for marker in forbidden:
        assert marker not in combined

    assert "send_secure_broker_hub_link" in commands
    assert "send_secure_broker_hub_link" in compat
    assert "SignalRankAI does not accept broker passwords in Telegram" in commands


def test_secure_broker_handoff_uses_one_time_first_party_activation() -> None:
    handoff = _source("signalrank_telegram/broker_linking.py")

    assert "create_telegram_activation" in handoff
    assert "/activate?token=" in handoff
    assert "Open secure Broker Hub" in handoff
    assert "Broker Hub → MetaTrader" in handoff
    assert "Linking an account never enables execution" in handoff
    assert "/verifybroker" in handoff
    assert "Prepare DEMO certification" in handoff


def test_web_remains_the_only_broker_secret_entry_surface() -> None:
    api = _source("web/platform_api.py")

    assert '@router.post("/broker/metatrader")' in api
    assert '@router.post("/broker/metatrader/secure-link")' in api
    assert "is_encryption_available()" in api
    assert "link_platform_metatrader_account" in api
    assert '"execution_enabled": False' in api
    assert "Trading is not enabled by connecting credentials" in api


def test_connect_broker_alias_is_compatibility_handoff_only() -> None:
    commands = _source("signalrank_telegram/commands.py")
    block = commands[
        commands.index("async def connect_broker_start"):
        commands.index("async def cancel_command")
    ]

    assert "send_secure_broker_hub_link" in block
    assert "states={}" in block
    assert "mt5_password" not in block
    assert "link_mt5_account(" not in block
    assert "ConversationHandler(" in block
