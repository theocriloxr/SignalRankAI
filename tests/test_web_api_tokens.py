import unittest
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestWebApiTokens(unittest.IsolatedAsyncioTestCase):
    async def test_rotate_and_revoke_token(self):
        from web.api import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            rotate = await client.post(
                "/auth/tokens/rotate",
                json={"telegram_user_id": 123456, "scope": "signals:read", "ttl_days": 1},
            )
            # DB may be unavailable in local test env; either behavior is acceptable for smoke.
            self.assertIn(rotate.status_code, {200, 503})
            if rotate.status_code == 200:
                token = rotate.json()["token"]
                revoke = await client.post("/auth/tokens/revoke", json={"token": token})
                self.assertEqual(revoke.status_code, 200)
