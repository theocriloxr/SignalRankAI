from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_openai_provider_status_is_secret_safe(monkeypatch) -> None:
    import services.openai_ai as ai

    secret = "sk-test-never-display-this"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("OPENAI_AI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_SIGNAL_REVIEW_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    status = ai.provider_status()

    assert status["key_configured"] is True
    assert status["available"] is True
    assert status["provider_order"] == ["openai", "gemini", "local"]
    assert status["fast_model"]
    assert status["deep_model"]
    serialized = json.dumps(status)
    assert secret not in serialized
    assert "OPENAI_API_KEY" not in serialized


@pytest.mark.asyncio
async def test_openai_connection_test_uses_minimal_structured_payload(monkeypatch) -> None:
    import services.openai_ai as ai

    captured = {}

    async def fake_structured_response(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "provider": "openai",
            "model": "gpt-5.6-terra",
            "latency_ms": 12.5,
            "data": {"connected": True, "message": "ok"},
        }

    monkeypatch.setattr(ai, "_structured_response", fake_structured_response)
    result = await ai.connection_test()

    assert result["connected"] is True
    assert captured["task"] == "signalrank_openai_connection_test"
    assert captured["payload"] == {"health_check": True, "contains_trading_data": False}
    assert captured["deep"] is False
    assert captured["schema"]["additionalProperties"] is False


def test_ai_operator_commands_are_registered_and_admin_gated() -> None:
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    policy = (ROOT / "core" / "tier_policy.py").read_text(encoding="utf-8")
    registry = json.loads(
        (ROOT / "requirements" / "command_registry.yaml").read_text(encoding="utf-8")
    )

    assert "async def ai_status_command" in commands
    assert "async def ai_test_command" in commands
    assert 'CommandHandler("ai_status", _audit_handler("ai_status", ai_status_command))' in bot
    assert 'CommandHandler("ai_test", _audit_handler("ai_test", ai_test_command))' in bot
    assert '"ai_status": Tier.ADMIN' in policy
    assert '"ai_test": Tier.ADMIN' in policy

    by_name = {row["canonical_name"]: row for row in registry["commands"]}
    assert by_name["ai_status"]["minimum_tier"] == "ADMIN"
    assert by_name["ai_test"]["minimum_tier"] == "ADMIN"
    assert registry["count"] == len(registry["commands"])
    assert registry["registration_count"] == 183


def test_ai_commands_never_accept_or_print_api_key_values() -> None:
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    start = commands.index("async def ai_status_command")
    end = commands.index("async def codex_audit_command", start)
    block = commands[start:end]

    assert "OPENAI_API_KEY" not in block
    assert "Set OPENAI_API_KEY as a Railway secret" in block
    assert "Secrets are never displayed" in block
