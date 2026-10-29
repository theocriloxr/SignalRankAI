"""Sign-in-link and reset emails are capped per account per hour (29 Oct 2026 threat model).

The requests are unauthenticated and the route limiter keys on a client-set
forwarded address, so anyone could flood a person's inbox. Real PostgreSQL;
skipped without one, required when SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert os.getenv("APP_ENV") == "test"
    assert parsed.host in {"127.0.0.1", "localhost"} and "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _emails(uid: int, template: str) -> int:
    from db.session import get_session

    async with get_session() as session:
        return int((await session.execute(text(
            "SELECT COUNT(*) FROM email_outbox WHERE user_id=:uid AND template=:template"
        ), {"uid": uid, "template": template})).scalar_one())


@pytest.mark.asyncio
async def test_link_and_reset_emails_stop_at_the_hourly_cap(isolated_postgres, monkeypatch):
    from db.session import get_session
    from services.platform.identity import create_email_account, request_magic_login, request_password_reset

    monkeypatch.setenv("ACCOUNT_EMAIL_MAX_PER_HOUR", "5")
    email = f"budget-{uuid4().hex[:10]}@example.test"
    async with get_session() as session:
        uid = await create_email_account(session, email=email, password="Budget-Test-29-Oct!", display_name="Budget")
        await session.commit()

    results = []
    for _ in range(7):
        async with get_session() as session:
            results.append(await request_magic_login(session, email=email.upper(), base_url="https://app.example.test"))
            await session.commit()
    assert [r is not None for r in results] == [True] * 5 + [False] * 2
    assert await _emails(uid, "magic_login") == 5

    async with get_session() as session:  # a separate budget per purpose
        assert await request_password_reset(session, email=email, base_url="https://app.example.test") is not None
        await session.commit()
    assert await _emails(uid, "password_reset") == 1


@pytest.mark.asyncio
async def test_the_http_reply_is_identical_when_capped(isolated_postgres, monkeypatch):
    from starlette.requests import Request

    from db.session import get_session
    from services.platform.identity import create_email_account
    from web.platform_api import EmailRequest, magic_link_request

    monkeypatch.setenv("ACCOUNT_EMAIL_MAX_PER_HOUR", "1")
    email = f"budget-{uuid4().hex[:10]}@example.test"
    async with get_session() as session:
        await create_email_account(session, email=email, password="Budget-Test-29-Oct!", display_name="Budget")
        await session.commit()
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/platform/auth/magic-link/request",
                       "headers": [(b"host", b"app.example.test")], "query_string": b"", "scheme": "https",
                       "server": ("app.example.test", 443), "client": ("127.0.0.1", 1)})
    first = await magic_link_request(EmailRequest(email=email), request)
    capped = await magic_link_request(EmailRequest(email=email), request)
    unknown = await magic_link_request(EmailRequest(email=f"nobody-{uuid4().hex[:8]}@example.test"), request)
    assert first == capped == unknown
