"""Multi-user isolation against the real platform API and a real PostgreSQL schema.

Several users with different tiers act concurrently through the actual FastAPI
routes, authenticated with real session tokens. Every user-owned resource is
created by its owner through the public API and then attacked by another user
through the same API. Hermetic mocks cannot satisfy these tests: they skip
without an isolated local PostgreSQL migrated to the current head, and fail if
SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def isolated_postgres(monkeypatch):
    from db.session import dispose_engine_for_event_loop, get_session
    from sqlalchemy import text

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql", "SQLite cannot certify isolation"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}, "integration mutations require a local isolated database"
    assert "test" in (parsed.database or "")
    monkeypatch.setenv("APP_AUTH_SECRET", "multi-user-isolation-test-secret-" * 2)
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


@pytest.fixture
def platform_app():
    from fastapi import FastAPI
    from web import platform_api

    app = FastAPI()
    app.include_router(platform_api.router, prefix="/api/v1")
    return app


@asynccontextmanager
async def _client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        yield client


async def _make_users(*tiers: str) -> list[dict]:
    """Create independent active users with their own session and bearer token."""
    from db.models import User
    from db.session import get_session
    from services.platform.identity import create_session_tokens

    users: list[dict] = []
    async with get_session() as session:
        for tier in tiers:
            user = User(username=f"isolation-{tier}-{uuid4().hex[:12]}", tier=tier)
            session.add(user)
            await session.flush()
            tokens = await create_session_tokens(session, user_id=user.id)
            users.append({"id": user.id, "tier": tier, "session_id": tokens.session_id,
                          "headers": {"Authorization": f"Bearer {tokens.access_token}"}})
        await session.commit()
    return users


async def test_concurrent_requests_never_mix_identities(isolated_postgres, platform_app):
    users = await _make_users("free", "premium", "vip")
    async with _client(platform_app) as client:
        plan = [users[i % len(users)] for i in range(30)]
        responses = await asyncio.gather(*(client.get("/api/v1/platform/me", headers=u["headers"]) for u in plan))
    for user, response in zip(plan, responses):
        assert response.status_code == 200, response.text
        assert int(response.json()["user"]["id"]) == user["id"]


async def test_owned_resources_cannot_be_read_changed_or_deleted_by_another_user(isolated_postgres, platform_app):
    owner, intruder = await _make_users("premium", "premium")
    async with _client(platform_app) as client:
        # The owner creates one of each user-owned resource through the real API.
        watchlist = await client.post("/api/v1/platform/watchlists", json={"name": "owner list"}, headers=owner["headers"])
        journal = await client.post("/api/v1/platform/journal", json={"notes": "owner private note"}, headers=owner["headers"])
        ticket = await client.post("/api/v1/platform/support/tickets",
                                   json={"subject": "owner ticket", "message": "private detail"}, headers=owner["headers"])
        alert = await client.post("/api/v1/platform/alerts",
                                  json={"asset": "BTCUSDT", "alert_type": "signal_generated", "channels": ["web"]},
                                  headers=owner["headers"])
        for created in (watchlist, journal, ticket, alert):
            assert created.status_code == 201, created.text
        watchlist_id = watchlist.json()["watchlist_id"]
        entry_id = journal.json()["journal_entry_id"]
        ticket_id = ticket.json()["ticket_id"]
        alert_id = alert.json()["alert_id"]

        h = intruder["headers"]
        # Direct-object access with guessed/leaked identifiers must fail as "not found".
        attempts = [
            await client.delete(f"/api/v1/platform/watchlists/{watchlist_id}", headers=h),
            await client.post(f"/api/v1/platform/watchlists/{watchlist_id}/items", json={"instrument_id": "BTCUSDT"}, headers=h),
            await client.delete(f"/api/v1/platform/journal/{entry_id}", headers=h),
            await client.get(f"/api/v1/platform/support/tickets/{ticket_id}", headers=h),
            await client.post(f"/api/v1/platform/support/tickets/{ticket_id}/messages", json={"message": "injected"}, headers=h),
            await client.delete(f"/api/v1/platform/alerts/{alert_id}", headers=h),
        ]
        assert [r.status_code for r in attempts] == [404] * len(attempts), [r.text for r in attempts]

        # Collections never include another user's records.
        for path, key, owned in (("watchlists", "watchlists", watchlist_id), ("journal", "entries", entry_id),
                                 ("support/tickets", "tickets", ticket_id), ("alerts", "alerts", alert_id)):
            listing = await client.get(f"/api/v1/platform/{path}", headers=h)
            assert listing.status_code == 200, listing.text
            assert owned not in json.dumps(listing.json()[key]), path

        # The owner's records are intact after the attack.
        owner_ticket = await client.get(f"/api/v1/platform/support/tickets/{ticket_id}", headers=owner["headers"])
        assert owner_ticket.status_code == 200
        assert [m["message"] for m in owner_ticket.json()["messages"]] == ["private detail"]
        owner_alerts = (await client.get("/api/v1/platform/alerts", headers=owner["headers"])).json()["alerts"]
        assert any(a["alert_id"] == alert_id and a["active"] is True for a in owner_alerts)
        owner_journal = (await client.get("/api/v1/platform/journal", headers=owner["headers"])).json()["entries"]
        assert any(e["journal_entry_id"] == entry_id for e in owner_journal)
        owner_lists = (await client.get("/api/v1/platform/watchlists", headers=owner["headers"])).json()["watchlists"]
        assert any(w["watchlist_id"] == watchlist_id for w in owner_lists)


async def test_signal_deliveries_and_notifications_are_per_recipient(isolated_postgres, platform_app):
    from db.models import Signal, SignalDelivery
    from db.session import get_session
    from sqlalchemy import text

    recipient, other = await _make_users("vip", "vip")
    signal_id = str(uuid4())
    notification_id = str(uuid4())
    async with get_session() as session:
        session.add(Signal(signal_id=signal_id, asset="ISOLATIONTEST", direction="long", timeframe="1h", entry=100,
                           stop_loss=99, take_profit="[102]", score=90, strategy_name="isolation", strategy_group="audit",
                           strength=1, created_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(hours=4)))
        await session.flush()
        session.add(SignalDelivery(user_id=recipient["id"], signal_id=signal_id, sent_ok=True, delivery_state="confirmed"))
        await session.execute(text(
            "INSERT INTO notification_events(notification_id,user_id,event_type,title,body) "
            "VALUES(:id,:uid,'signal','private signal','delivered only to the recipient')"),
            {"id": notification_id, "uid": recipient["id"]})
        await session.commit()

    async with _client(platform_app) as client:
        # One generated signal is not "delivered to everyone": only the recipient may open it.
        assert (await client.get(f"/api/v1/platform/signals/{signal_id}", headers=recipient["headers"])).status_code == 200
        assert (await client.get(f"/api/v1/platform/signals/{signal_id}", headers=other["headers"])).status_code == 404
        other_feed = await client.get("/api/v1/platform/signals", headers=other["headers"])
        assert other_feed.status_code == 200 and signal_id not in json.dumps(other_feed.json())
        feedback = await client.post(f"/api/v1/platform/signals/{signal_id}/feedback", json={"rating": 1}, headers=other["headers"])
        assert feedback.status_code in {403, 404}

        assert (await client.post(f"/api/v1/platform/notifications/{notification_id}/read", headers=other["headers"])).status_code == 404
        other_notes = await client.get("/api/v1/platform/notifications", headers=other["headers"])
        assert notification_id not in json.dumps(other_notes.json())
        still_unread = await client.get("/api/v1/platform/notifications", headers=recipient["headers"])
        mine = [n for n in still_unread.json()["notifications"] if n["notification_id"] == notification_id]
        assert mine and mine[0]["read_at"] is None


async def test_sessions_profiles_and_payments_cannot_cross_users(isolated_postgres, platform_app):
    from db.models import PaymentReceipt
    from db.session import get_session

    first, second = await _make_users("premium", "premium")
    reference = "iso-" + uuid4().hex[:16]
    async with get_session() as session:
        session.add(PaymentReceipt(receipt_number="R-" + uuid4().hex[:12], user_id=first["id"],
                                   payment_reference=reference, plan="premium", amount=1000.0))
        await session.commit()

    async with _client(platform_app) as client:
        # Another user's device session cannot be revoked; the owner's token keeps working.
        revoke = await client.delete(f"/api/v1/platform/devices/{first['session_id']}", headers=second["headers"])
        assert revoke.status_code == 404
        assert (await client.get("/api/v1/platform/me", headers=first["headers"])).status_code == 200

        # A profile change by one user never alters another user's profile.
        before = (await client.get("/api/v1/platform/trading-profile", headers=second["headers"])).json()["preferences"]
        options = (await client.get("/api/v1/platform/trading-profile", headers=first["headers"])).json()["options"]
        current = (await client.get("/api/v1/platform/trading-profile", headers=first["headers"])).json()["preferences"]
        choice = next(p for p in options["risk_profiles"] if p != current.get("risk_profile"))
        changed = await client.put("/api/v1/platform/trading-profile", json={"risk_profile": choice}, headers=first["headers"])
        assert changed.status_code == 200, changed.text
        assert changed.json()["preferences"]["risk_profile"] == choice
        reloaded = (await client.get("/api/v1/platform/trading-profile", headers=first["headers"])).json()["preferences"]
        assert reloaded["risk_profile"] == choice, "saved profile must survive a reload"
        after = (await client.get("/api/v1/platform/trading-profile", headers=second["headers"])).json()["preferences"]
        assert after == before

        # Billing records and refund requests stay with the paying account.
        second_billing = (await client.get("/api/v1/platform/billing", headers=second["headers"])).json()
        assert reference not in json.dumps(second_billing)
        refund = await client.post("/api/v1/platform/billing/refund-request",
                                   json={"payment_reference": reference, "reason": "not mine"}, headers=second["headers"])
        assert refund.status_code in {403, 404}
        first_billing = (await client.get("/api/v1/platform/billing", headers=first["headers"])).json()
        assert reference in json.dumps(first_billing)


async def test_delivery_cooldowns_are_scoped_to_each_user(isolated_postgres):
    from engine.signal_deduplicator import check_user_asset_cooldown, set_user_asset_cooldown

    first, second = await _make_users("free", "free")
    asset = "ISO" + uuid4().hex[:6].upper() + "USDT"
    assert check_user_asset_cooldown(first["id"], asset, "long") is False
    set_user_asset_cooldown(first["id"], asset, "long", "free")
    assert check_user_asset_cooldown(first["id"], asset, "long") is True
    assert check_user_asset_cooldown(second["id"], asset, "long") is False
