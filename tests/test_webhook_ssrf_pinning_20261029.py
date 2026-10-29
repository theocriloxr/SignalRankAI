"""Outbound webhooks connect only to the address that passed validation (29 Oct 2026 threat model).

Before: the destination was resolved and checked, then httpx resolved it again
to connect, so a DNS-rebinding host could pass the check with a public address
and receive the POST on an internal one. Shared (100.64/10) addresses also
passed because only ``is_private`` was checked.
"""
from __future__ import annotations

import socket

import httpx
import pytest

from services.platform import webhooks


def _resolver(*answers: str):
    calls = {"n": 0}

    def fake_getaddrinfo(host, port, *args, **kwargs):
        answer = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        family = socket.AF_INET6 if ":" in answer else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (answer, 0))]

    return fake_getaddrinfo, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["100.64.10.1", "169.254.169.254", "10.0.0.5", "fd12::1", "::ffff:127.0.0.1"])
async def test_non_public_destinations_are_refused(monkeypatch, address):
    monkeypatch.setenv("ENVIRONMENT", "production")
    fake, _ = _resolver(address)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    with pytest.raises(ValueError, match="private"):
        await webhooks.validate_webhook_destination("https://hooks.example.com/in")


def test_pinned_request_keeps_the_hostname_for_tls_and_host():
    url, extensions, host = webhooks.pinned_request("https://hooks.example.com/in?x=1", {"93.184.216.34"})
    assert url == "https://93.184.216.34/in?x=1"
    assert extensions == {"sni_hostname": "hooks.example.com"} and host == {"Host": "hooks.example.com"}
    url, _, host = webhooks.pinned_request("https://hooks.example.com:8443/in", {"2606:2800:220:1::1", "93.184.216.34"})
    assert url == "https://93.184.216.34:8443/in" and host == {"Host": "hooks.example.com:8443"}  # IPv4 preferred
    url, _, _ = webhooks.pinned_request("https://hooks.example.com/in", {"2606:2800:220:1::1"})
    assert url == "https://[2606:2800:220:1::1]/in"
    assert webhooks.pinned_request("http://localhost:8000/in", None) == ("http://localhost:8000/in", {}, {})


@pytest.mark.asyncio
async def test_a_rebinding_answer_after_validation_never_receives_the_delivery(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    # First lookup (validation) is public; any later lookup would point inside.
    fake, calls = _resolver("93.184.216.34", "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    monkeypatch.setattr(webhooks, "decrypt_secret", lambda _value: "whsec_test")
    stored: list[dict] = []

    async def store(delivery_id, **kwargs):
        stored.append(kwargs)

    monkeypatch.setattr(webhooks, "_store_result", store)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    item = {"webhook_delivery_id": "d1", "attempt_count": 1, "url": "https://hooks.example.com/in",
            "encrypted_secret": "x", "event_id": "e1", "event_type": "signal.created", "payload": {},
            "idempotency_key": "k1"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await webhooks._deliver_one(client, item) is True
    assert calls["n"] == 1  # resolved once; the connection target is that answer, not a new lookup
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "hooks.example.com"
    assert seen[0].extensions["sni_hostname"] == "hooks.example.com"
    assert stored == [{"delivered": True, "status_code": 204, "response_excerpt": None, "attempts": 1}]


@pytest.mark.asyncio
async def test_a_destination_that_now_resolves_inside_is_not_contacted(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    fake, _ = _resolver("10.1.2.3")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    stored: list[dict] = []

    async def store(delivery_id, **kwargs):
        stored.append(kwargs)

    monkeypatch.setattr(webhooks, "_store_result", store)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be reached
        raise AssertionError("an internal address was contacted")

    item = {"webhook_delivery_id": "d2", "attempt_count": 1, "url": "https://hooks.example.com/in",
            "encrypted_secret": "x", "event_id": "e2", "event_type": "signal.created", "payload": {},
            "idempotency_key": "k2"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await webhooks._deliver_one(client, item) is False
    assert stored and stored[0]["delivered"] is False and "private_address_blocked" in stored[0]["error"]
