"""Self-service data export and account-deletion requests on real PostgreSQL.

The export must contain only the caller's records and never credentials; the
deletion request must open one audited review and delete nothing. Like the
multi-user isolation suite, these tests skip without an isolated local
PostgreSQL and fail if SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import inspect
import json
import time
from pathlib import Path

import pytest

from tests.test_multi_user_isolation_postgres_20261024 import (  # noqa: F401 - fixtures
    _client,
    _make_users,
    isolated_postgres,
    platform_app,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_export_contains_only_the_callers_records_and_no_secrets(isolated_postgres, platform_app):
    owner, other = await _make_users("premium", "premium")
    async with _client(platform_app) as client:
        made = await client.post("/api/v1/platform/watchlists", json={"name": "export-owner-list"}, headers=owner["headers"])
        ticket = await client.post("/api/v1/platform/support/tickets",
                                   json={"subject": "export ticket", "message": "owner-only detail"}, headers=owner["headers"])
        assert made.status_code == 201 and ticket.status_code == 201

        mine = await client.get("/api/v1/platform/account/export", headers=owner["headers"])
        theirs = await client.get("/api/v1/platform/account/export", headers=other["headers"])
    assert mine.status_code == 200, mine.text
    assert theirs.status_code == 200, theirs.text
    data, foreign = mine.json(), json.dumps(theirs.json())

    assert data["user_id"] == owner["id"]
    sections = data["sections"]
    assert any(w["name"] == "export-owner-list" for w in sections["watchlists"]["watchlists"])
    assert [m["message"] for m in sections["support_messages"]] == ["owner-only detail"]
    assert "export-owner-list" not in foreign and "owner-only detail" not in foreign

    raw = json.dumps(data).lower()
    for secret in ("password_hash", "secret_hash", "key_hash", "encrypted_secret", "access_token", "refresh_token"):
        assert secret not in raw, secret
    # Plan-gated sections are reported, never silently emptied.
    for name, reason in data["unavailable"].items():
        assert name not in sections and reason, name


@pytest.mark.asyncio
async def test_deletion_request_needs_the_phrase_opens_one_review_and_deletes_nothing(isolated_postgres, platform_app):
    (user,) = await _make_users("free")
    h = user["headers"]
    async with _client(platform_app) as client:
        wrong = await client.post("/api/v1/platform/account/deletion-request", json={"confirm_phrase": "yes"}, headers=h)
        assert wrong.status_code == 422

        first = await client.post("/api/v1/platform/account/deletion-request",
                                  json={"confirm_phrase": "DELETE MY ACCOUNT", "reason": "testing"}, headers=h)
        again = await client.post("/api/v1/platform/account/deletion-request",
                                  json={"confirm_phrase": "DELETE MY ACCOUNT"}, headers=h)
        assert first.status_code == 202, first.text
        assert first.json()["already_requested"] is False and first.json()["retained_records"]
        assert again.status_code == 202
        assert again.json()["ticket_id"] == first.json()["ticket_id"]
        assert again.json()["already_requested"] is True

        # The account still works and the review is visible to its owner.
        assert (await client.get("/api/v1/platform/me", headers=h)).status_code == 200
        tickets = (await client.get("/api/v1/platform/support/tickets", headers=h)).json()["tickets"]
        reviews = [t for t in tickets if t["category"] == "privacy_deletion"]
        assert len(reviews) == 1 and reviews[0]["status"] == "open"


@pytest.mark.asyncio
async def test_deletion_request_requires_a_recent_sign_in(isolated_postgres, platform_app, monkeypatch):
    import time as real_time
    from types import SimpleNamespace

    from services.platform import identity

    (user,) = await _make_users("free")
    # A still-valid token whose sign-in happened three hours ago.
    monkeypatch.setattr(identity, "time", SimpleNamespace(time=lambda: real_time.time() - 3 * 3600))
    stale = identity.encode_access_token(user["id"], ttl_minutes=600, session_id=user["session_id"])
    monkeypatch.setattr(identity, "time", real_time)
    async with _client(platform_app) as client:
        assert (await client.get("/api/v1/platform/me", headers={"Authorization": f"Bearer {stale}"})).status_code == 200
        response = await client.post("/api/v1/platform/account/deletion-request",
                                     json={"confirm_phrase": "DELETE MY ACCOUNT"},
                                     headers={"Authorization": f"Bearer {stale}"})
    assert response.status_code == 403


@pytest.mark.parametrize("zone", ["America/New_York", "Asia/Tokyo"])
@pytest.mark.skipif(not hasattr(time, "tzset"),
                    reason="time.tzset is POSIX-only; the host-offset regression runs on Linux and macOS")
@pytest.mark.asyncio
async def test_recent_sign_in_age_does_not_depend_on_host_timezone(isolated_postgres, platform_app, monkeypatch, zone):
    """Regression: auth age used naive utcnow().timestamp(), shifted by the host UTC offset."""
    import time as real_time

    (user,) = await _make_users("free")
    monkeypatch.setenv("TZ", zone)
    real_time.tzset()
    try:
        async with _client(platform_app) as client:
            response = await client.post("/api/v1/platform/account/deletion-request",
                                         json={"confirm_phrase": "DELETE MY ACCOUNT"}, headers=user["headers"])
    finally:
        monkeypatch.undo()
        real_time.tzset()
    assert response.status_code == 202, response.text


def test_deletion_request_never_issues_destructive_sql():
    from web import platform_api

    source = inspect.getsource(platform_api.request_account_deletion)
    assert "DELETE FROM" not in source.upper()
    assert "UPDATE USERS" not in source.upper()
    assert "_require_recent_auth(user)" in source
