from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_telegram_api_key_command_never_creates_or_reveals_secret() -> None:
    for relative in (
        "signalrank_telegram/commands.py",
        "signalrank_telegram/account_commands.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        start = source.index("async def apikey_command")
        end_candidates = [
            value for value in (
                source.find("\nasync def ", start + 10),
                source.find("\ndef ", start + 10),
                source.find("\n__all__", start + 10),
                source.find("# Basic translation dictionary", start + 10),
            )
            if value > start
        ]
        end = min(end_candidates) if end_candidates else len(source)
        block = source[start:end]
        assert "create_api_token" not in block
        assert "_rotate_api_token_for_user" not in block
        assert "generate_api_key" not in block
        assert "Your API key:" not in block
        assert "Your new API key:" not in block
        assert "/app/settings" in block


def test_web_api_key_creation_requires_recent_server_derived_auth() -> None:
    source = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    current = source[source.index("async def current_user("):source.index("async def _create_login_response")]
    create = source[source.index("async def create_api_key("):source.index('@router.delete("/api-keys/{key_id}")')]
    helper = source[source.index("def _require_recent_auth("):source.index("async def _create_login_response")]

    assert "SELECT created_at FROM user_sessions" in current
    assert "(now - authenticated_at).total_seconds()" in current
    assert 'user["auth_age_seconds"]' in current
    assert "SENSITIVE_ACTION_RECENT_AUTH_SECONDS" in helper
    assert "status_code=403" in helper
    assert "_require_recent_auth(user)" in create
    assert '"api_key": raw_key' in create
    assert "This key is shown once" in create
