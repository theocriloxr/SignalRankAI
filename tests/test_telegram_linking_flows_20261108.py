"""Telegram sign-up/sign-in and app <-> Telegram linking (owner request, 8 Nov 2026).

Fixed: bot links (/app, broker hub, legacy dashboard) preferred a leftover
RAILWAY_PUBLIC_DOMAIN over APP_BASE_URL (production left Railway on 29 Oct);
the app's "Open in Telegram" deep link needed BOT_USERNAME set; the web page
did not notice a completed link. Both flows run end to end on PostgreSQL here.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from core.app_url import public_app_base_url

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_configured_app_address_beats_a_leftover_railway_domain(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://www.signalrank.criloxsolutions.com/")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "signalrank-old.up.railway.app")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert public_app_base_url() == "https://www.signalrank.criloxsolutions.com"
    monkeypatch.delenv("APP_BASE_URL")
    assert public_app_base_url() == "https://signalrank-old.up.railway.app"


def test_bot_username_from_getme_when_not_configured(monkeypatch):
    import httpx

    from web import platform_api as api

    monkeypatch.delenv("BOT_USERNAME", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(api, "_BOT_USERNAME_CACHE", {})

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "result": {"username": "SignalRankAIBot"}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert url.endswith("/getMe")
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert asyncio.run(api._telegram_bot_username()) == "SignalRankAIBot"


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_both_linking_flows_on_postgres(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    tg_new, tg_link = 900_000_000 + int(uuid4().int % 1_000_000), 910_000_000 + int(uuid4().int % 1_000_000)
    email_a = f"tg-flow-{uuid4().hex[:8]}@example.com"
    email_b = f"tg-flow-{uuid4().hex[:8]}@example.com"

    async def app_to_telegram() -> str:
        from db.session import dispose_engine_for_event_loop, get_session
        from services.platform.identity import (
            complete_telegram_link_request, create_email_account, create_telegram_link_request,
        )

        try:
            async with get_session() as session:
                uid = await create_email_account(session, email=email_b, password="Linked-flow-9", display_name="B")
                request = await create_telegram_link_request(session, user_id=uid)
                await session.commit()
            async with get_session() as session:
                result = await complete_telegram_link_request(session, token_or_code=request.code,
                                                              telegram_user_id=tg_link, username="flowb")
                await session.commit()
            async with get_session() as session:
                linked = (await session.execute(text("SELECT telegram_user_id FROM users WHERE id=:u"),
                                                {"u": uid})).scalar_one()
            assert result.status == "linked" and int(linked) == tg_link
            return "ok"
        finally:
            await dispose_engine_for_event_loop()

    async def new_telegram_activation() -> str:
        from db.session import dispose_engine_for_event_loop, get_session
        from services.platform.identity import create_telegram_activation

        try:
            async with get_session() as session:
                activation = await create_telegram_activation(session, telegram_user_id=tg_new, username="flowa")
                await session.commit()
            return activation.code
        finally:
            await dispose_engine_for_event_loop()

    async def cleanup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            ids = [r[0] for r in (await conn.execute(text(
                "SELECT id FROM users WHERE telegram_user_id = ANY(:t) OR lower(primary_email) = ANY(:e)"),
                {"t": [tg_new, tg_link], "e": [email_a, email_b]})).all()]
            for table in ("login_challenges", "account_link_requests", "user_identities", "auth_sessions",
                          "security_events", "notification_preferences", "user_acquisition", "email_outbox"):
                try:
                    async with conn.begin_nested():
                        column = "requesting_user_id" if table == "account_link_requests" else "user_id"
                        await conn.execute(text(f"DELETE FROM {table} WHERE {column} = ANY(:ids)"), {"ids": ids})
                except Exception:
                    pass
            try:
                async with conn.begin_nested():
                    await conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
            except Exception:
                pass
        await engine.dispose()

    try:
        assert asyncio.run(app_to_telegram()) == "ok"
        code = asyncio.run(new_telegram_activation())
        from web.app import app

        host = "https://signalrank.criloxsolutions.com"
        client = TestClient(app, base_url=host)
        done = client.post("/api/v1/platform/auth/telegram/complete", headers={"origin": host}, json={
            "token_or_code": code, "email": email_a, "password": "Telegram-flow-9", "client_type": "web",
            "platform_terms_accepted": True, "privacy_acknowledged": True, "age_eligibility_confirmed": True})
        assert done.status_code in (200, 201), done.text
        assert done.json()["user"]["telegram_user_id"] == tg_new
        fresh = TestClient(app, base_url=host)
        login = fresh.post("/api/v1/platform/auth/login", headers={"origin": host},
                           json={"email": email_a, "password": "Telegram-flow-9", "client_type": "web"})
        assert login.status_code == 200, login.text
    finally:
        asyncio.run(cleanup())
