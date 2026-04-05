import unittest
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RailwayMonolithContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_and_ready_endpoints(self):
        from railway_main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            h = await client.get("/health")
            self.assertIn(h.status_code, {200})
            hz = await client.get("/healthz")
            self.assertIn(hz.status_code, {200})
