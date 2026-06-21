from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_upgrade_message_escapes_markdown_pipe() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert ("💎 VIP Monthly — ₦40,000 \\|" in source) or ("💎 VIP Monthly — ₦40,000 \\\\|" in source)
    assert "parse_mode=\"MarkdownV2\"" in source


def test_tiers_command_uses_live_pricing_envs() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert 'os.getenv("PREMIUM_MONTHLY_PRICE_NGN", os.getenv("PREMIUM_PRICE_NGN", "24000"))' in source
    assert 'os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000"))' in source


def test_buy_extra_signals_removed_from_command_access() -> None:
    source = (ROOT / "signalrank_telegram" / "command_access.py").read_text(encoding="utf-8")
    assert "buy_extra_signals" not in source


@pytest.mark.asyncio
async def test_gemini_audit_command_uses_session_and_helper() -> None:
    from signalrank_telegram.commands import gemini_audit_command

    class _Message:
        def __init__(self) -> None:
            self.replies: list[str] = []

        async def reply_text(self, text: str) -> None:
            self.replies.append(text)

    class _Update:
        def __init__(self) -> None:
            self.effective_user = MagicMock(id=999)
            self.message = _Message()

    class _SessionCM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    update = _Update()
    context = MagicMock()
    context.args = ["7"]

    with patch("signalrank_telegram.commands._is_admin", return_value=True), patch(
        "signalrank_telegram.commands.get_session", return_value=_SessionCM()
    ), patch("services.gemini_ml.audit_recent", new=AsyncMock(return_value={"ok": True, "recent_losses": [1], "recent_rejections": [2, 3]})) as audit_mock:
        await gemini_audit_command(update, context)

    assert audit_mock.await_count == 1
    assert update.message.replies == ["Recent losses: 1, recent rejections: 2"]
