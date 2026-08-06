from __future__ import annotations

import hashlib
import hmac

import pytest

from services.platform.webhooks import validate_webhook_destination, webhook_signature


def test_webhook_signature_is_hmac_sha256() -> None:
    body = b'{"id":"evt_1"}'
    timestamp = "1700000000"
    expected = "v1=" + hmac.new(b"secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    assert webhook_signature("secret", timestamp, body) == expected


@pytest.mark.asyncio
async def test_webhook_destination_rejects_private_https_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="private"):
        await validate_webhook_destination("https://127.0.0.1/hook")


@pytest.mark.asyncio
async def test_webhook_destination_rejects_http_in_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="https"):
        await validate_webhook_destination("http://example.com/hook")
