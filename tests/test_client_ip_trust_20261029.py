"""Client addresses come only from sources a client cannot forge (29 Oct 2026).

Rate limits, security events and the Paystack IP allowlist used the first
X-Forwarded-For value, which the client controls. Railway's edge sets
X-Real-IP to the client's remote address (Railway public networking specs).
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from core import client_ip as ci

SECRET = "s" * 40


def _request(headers: dict[str, str], peer: str | None = "10.250.0.9"):
    return SimpleNamespace(headers={k.lower(): v for k, v in headers.items()},
                           client=SimpleNamespace(host=peer) if peer else None)


@pytest.fixture
def on_railway(monkeypatch):
    for name in ("TRUSTED_CLIENT_IP_HEADER", "SIGNALRANK_CLIENT_IP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")


def test_a_forged_forwarded_for_never_wins_on_railway(on_railway):
    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "203.0.113.7"})
    assert ci.resolve_client_ip(request) == ("203.0.113.7", "x-real-ip")


def test_off_railway_forwarding_headers_are_ignored(monkeypatch):
    for name in ("TRUSTED_CLIENT_IP_HEADER", "SIGNALRANK_CLIENT_IP_SECRET", "RAILWAY_ENVIRONMENT",
                 "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID"):
        monkeypatch.delenv(name, raising=False)
    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "203.0.113.7"}, peer="127.0.0.1")
    assert ci.resolve_client_ip(request) == ("127.0.0.1", "socket")


def test_signed_proxy_address_survives_a_second_edge_hop(on_railway, monkeypatch):
    monkeypatch.setenv("SIGNALRANK_CLIENT_IP_SECRET", SECRET)
    ts = str(int(time.time()))
    signed = {"x-signalrank-client-ip": "198.51.100.23", "x-signalrank-client-ip-ts": ts,
              "x-signalrank-client-ip-signature": ci.client_ip_signature(SECRET, "198.51.100.23", ts),
              "x-real-ip": "34.1.2.3"}  # the edge's view: our web server's egress address
    assert ci.resolve_client_ip(_request(signed)) == ("198.51.100.23", "signed_proxy")


@pytest.mark.parametrize("change", ["bad-signature", "stale", "wrong-secret", "not-an-ip", "no-secret"])
def test_invalid_signed_addresses_fall_back_to_the_edge_header(on_railway, monkeypatch, change):
    monkeypatch.setenv("SIGNALRANK_CLIENT_IP_SECRET", SECRET)
    ip, ts = "198.51.100.23", str(int(time.time()))
    signature = ci.client_ip_signature(SECRET, ip, ts)
    if change == "bad-signature":
        signature = "0" * 64
    elif change == "stale":
        ts = str(int(time.time()) - 3600)
        signature = ci.client_ip_signature(SECRET, ip, ts)
    elif change == "wrong-secret":
        signature = ci.client_ip_signature("x" * 40, ip, ts)
    elif change == "not-an-ip":
        ip = "evil.example"
        signature = ci.client_ip_signature(SECRET, ip, ts)
    elif change == "no-secret":
        monkeypatch.delenv("SIGNALRANK_CLIENT_IP_SECRET")
    request = _request({"x-signalrank-client-ip": ip, "x-signalrank-client-ip-ts": ts,
                        "x-signalrank-client-ip-signature": signature, "x-real-ip": "203.0.113.7"})
    assert ci.resolve_client_ip(request) == ("203.0.113.7", "x-real-ip")


def test_signature_format_matches_the_web_proxy():
    # frontend/scripts/client-address.test.mjs asserts the same vector with node:crypto.
    assert ci.client_ip_signature(SECRET, "203.0.113.7", "1800000000") == (
        "6b807005bcbcb7ab21745b78432f2679c2c437e6531047aa4086872de563f977")


def test_explicit_forwarded_for_uses_the_nearest_proxy_entry(monkeypatch):
    monkeypatch.setenv("TRUSTED_CLIENT_IP_HEADER", "x-forwarded-for")
    monkeypatch.delenv("SIGNALRANK_CLIENT_IP_SECRET", raising=False)
    request = _request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
    assert ci.resolve_client_ip(request) == ("203.0.113.7", "x-forwarded-for")


def test_garbage_values_are_ignored(on_railway):
    assert ci.resolve_client_ip(_request({"X-Real-IP": "<script>"}, peer="10.0.0.2")) == ("10.0.0.2", "socket")
    assert ci.resolve_client_ip(_request({}, peer="testclient")) == (None, "socket")


def test_rate_limit_key_ignores_forged_forwarded_for(on_railway):
    from web.app import rate_limit_key

    base = {"X-Real-IP": "203.0.113.7", "User-Agent": "ua"}
    a = rate_limit_key(_request({**base, "X-Forwarded-For": "1.1.1.1"}), "platform_auth")
    b = rate_limit_key(_request({**base, "X-Forwarded-For": "2.2.2.2"}), "platform_auth")
    c = rate_limit_key(_request({**base, "X-Real-IP": "203.0.113.8"}), "platform_auth")
    assert a == b != c


def test_security_events_and_paystack_use_the_trusted_resolver():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    api = (root / "web" / "platform_api.py").read_text(encoding="utf-8")
    paystack = (root / "payments" / "paystack_webhook.py").read_text(encoding="utf-8")
    assert "from core.client_ip import client_ip" in api
    assert 'request.headers.get("x-forwarded-for")\n    if forwarded' not in api
    assert "_trusted_client_ip(request)" in paystack and 'X-Forwarded-For", "").split(",")[0]' not in paystack


@pytest.mark.asyncio
async def test_request_identity_is_owner_only_and_reports_the_source(on_railway):
    from fastapi import HTTPException

    from web.platform_api import operator_request_identity

    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "203.0.113.7", "X-Railway-Edge": "cdg1"})
    report = await operator_request_identity(request, user={"id": 1, "tier": "owner"})
    assert report["client_ip"] == "203.0.113.7" and report["source"] == "x-real-ip"
    assert report["x_forwarded_for_received"] == "1.2.3.4" and report["railway_edge"] == "cdg1"
    assert report["signed_proxy_configured"] is False
    for tier in ("admin", "premium", "free"):
        with pytest.raises(HTTPException) as refused:
            await operator_request_identity(request, user={"id": 2, "tier": tier})
        assert refused.value.status_code == 403
