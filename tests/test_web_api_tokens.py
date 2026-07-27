import unittest
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummySession:
    async def commit(self):
        return None


@asynccontextmanager
async def _dummy_session():
    yield _DummySession()


class TestWebApiTokens(unittest.IsolatedAsyncioTestCase):
    async def test_missing_authentication_returns_401_when_token_service_is_available(self):
        from web import api as api_module

        transport = httpx.ASGITransport(app=api_module.app)
        with (
            patch.object(api_module, "is_db_configured", return_value=True),
            patch.object(api_module.state, "rate_limited", new=AsyncMock(return_value=False)),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/tokens/rotate",
                    json={"scope": "signals:read", "ttl_days": 1},
                )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "API key required")

    async def test_invalid_authentication_returns_401(self):
        from web import api as api_module

        transport = httpx.ASGITransport(app=api_module.app)
        with (
            patch.object(api_module, "is_db_configured", return_value=True),
            patch.object(api_module.state, "rate_limited", new=AsyncMock(return_value=False)),
            patch.object(api_module, "get_session", side_effect=lambda: _dummy_session()),
            patch.object(api_module, "get_api_token_owner", new=AsyncMock(return_value=None)),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/tokens/rotate",
                    headers={"X-API-Key": "srk_invalid_invalid_invalid_invalid"},
                    json={"scope": "signals:read", "ttl_days": 1},
                )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid, expired, or revoked API key")

    async def test_authenticated_rotate_and_revoke_token(self):
        from web import api as api_module

        owner_id = 123456
        app = api_module.app
        app.dependency_overrides[api_module.get_user_by_apikey] = lambda: owner_id
        created_tokens: list[str] = []

        async def _create(_session, *, telegram_user_id, raw_token, scope, expires_at):
            self.assertEqual(telegram_user_id, owner_id)
            self.assertEqual(scope, "signals:read")
            self.assertIsNotNone(expires_at)
            created_tokens.append(raw_token)
            return SimpleNamespace(token_id="tok-1")

        async def _owner(_session, raw_token, required_scope="signals:read"):
            return owner_id if raw_token in created_tokens else None

        async def _revoke(_session, raw_token):
            return raw_token in created_tokens

        transport = httpx.ASGITransport(app=app)
        try:
            with (
                patch.object(api_module, "get_session", side_effect=lambda: _dummy_session()),
                patch.object(api_module, "create_api_token", new=AsyncMock(side_effect=_create)),
                patch.object(api_module, "get_api_token_owner", new=AsyncMock(side_effect=_owner)),
                patch.object(api_module, "revoke_api_token", new=AsyncMock(side_effect=_revoke)),
            ):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    rotate = await client.post(
                        "/auth/tokens/rotate",
                        json={"scope": "signals:read", "ttl_days": 1},
                    )
                    self.assertEqual(rotate.status_code, 200, rotate.text)
                    token = rotate.json()["token"]
                    self.assertTrue(token.startswith("srk_"))
                    self.assertGreaterEqual(len(token), 40)

                    revoke = await client.post(
                        "/auth/tokens/revoke",
                        json={"token": token},
                    )
                    self.assertEqual(revoke.status_code, 200, revoke.text)
                    self.assertTrue(revoke.json()["revoked"])
        finally:
            app.dependency_overrides.clear()

    async def test_cannot_revoke_another_users_token(self):
        from web import api as api_module

        app = api_module.app
        app.dependency_overrides[api_module.get_user_by_apikey] = lambda: 123456
        transport = httpx.ASGITransport(app=app)
        try:
            with (
                patch.object(api_module, "get_session", side_effect=lambda: _dummy_session()),
                patch.object(api_module, "get_api_token_owner", new=AsyncMock(return_value=999999)),
            ):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/auth/tokens/revoke",
                        json={"token": "srk_" + "x" * 40},
                    )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"], "Cannot revoke another user's token")
        finally:
            app.dependency_overrides.clear()
