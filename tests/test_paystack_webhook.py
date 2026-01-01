import hashlib
import hmac
import os
import unittest

import httpx


class TestPaystackWebhook(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["PAYSTACK_WEBHOOK_SECRET"] = "test_secret"
        os.environ["PAYMENTS_ENABLED"] = "false"

    async def test_rejects_missing_signature(self):
        from web.app import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/webhooks/paystack", json={"event": "charge.success", "data": {"reference": "x"}})
            self.assertEqual(resp.status_code, 400)

    async def test_accepts_valid_signature_payments_disabled(self):
        from web.app import app

        body = b'{"event":"charge.success","data":{"reference":"TEST_REF"}}'
        sig = hmac.new(b"test_secret", body, hashlib.sha512).hexdigest()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/paystack",
                content=body,
                headers={"x-paystack-signature": sig, "content-type": "application/json"},
            )
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertTrue(payload["received"])
            # payments disabled => no external verify, so "verified" remains False
            self.assertFalse(payload["verified"])


if __name__ == "__main__":
    unittest.main()
