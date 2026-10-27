"""Security headers on responses served directly by the API (27 Oct 2026).

A local probe showed authenticated JSON from web.app with no nosniff, no
no-store and no HSTS. The Next.js proxy adds them for browser traffic, but
production also serves this app directly (legacy workspace, mobile, API keys).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app


def _client(scheme: str = "http") -> TestClient:
    return TestClient(app, base_url=f"{scheme}://testserver")


def test_direct_api_responses_carry_baseline_headers(monkeypatch):
    monkeypatch.delenv("SECURITY_HSTS_ENABLED", raising=False)
    response = _client().get("/api/v1/platform/me")
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert "strict-transport-security" not in response.headers


def test_hsts_only_over_https_and_can_be_disabled(monkeypatch):
    monkeypatch.delenv("SECURITY_HSTS_ENABLED", raising=False)
    secure = _client("https").get("/version")
    assert secure.headers["strict-transport-security"] == "max-age=31536000"
    assert "includesubdomains" not in secure.headers["strict-transport-security"].lower()
    forwarded = _client().get("/version", headers={"X-Forwarded-Proto": "https"})
    assert forwarded.headers["strict-transport-security"] == "max-age=31536000"
    monkeypatch.setenv("SECURITY_HSTS_ENABLED", "0")
    assert "strict-transport-security" not in _client("https").get("/version").headers


def test_non_account_routes_keep_their_own_caching():
    response = _client().get("/version")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("cache-control") != "private, no-store, max-age=0"


def test_frontend_sends_hsts_without_subdomains():
    from pathlib import Path

    config = (Path(__file__).resolve().parents[1] / "frontend" / "next.config.ts").read_text(encoding="utf-8")
    assert '{ key: "Strict-Transport-Security", value: "max-age=31536000" }' in config
