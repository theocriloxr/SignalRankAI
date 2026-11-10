"""Verification-email spam (owner report, 10 Nov 2026: "it is spamming verification emails").

Root cause: the outbox "mark sent" update used one parameter as both the varchar
column and a text comparison, which PostgreSQL rejects ("inconsistent types
deduced for parameter $1"). Sent rows stayed 'sending'; after the 5-minute lease
they went back to 'retry' and were sent again while the 30-minute link was
valid. Also: at most one verification email per account per 10 minutes.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")
pytestmark = pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")


def _url(monkeypatch):
    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_sent_email_is_marked_sent_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _url(monkeypatch)
    email_id = str(uuid4())

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from services.platform.email_delivery import _record_delivery

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO email_outbox(email_id,recipient,template,subject,plain_body,status) "
                    "VALUES (:e,'x@example.invalid','verify_email','s','b','sending')"), {"e": email_id})
            await _record_delivery(email_id, "sent", None, 0)
            async with engine.begin() as conn:
                return (await conn.execute(text(
                    "SELECT status, sent_at IS NOT NULL FROM email_outbox WHERE email_id=:e"), {"e": email_id})).one()
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM email_outbox WHERE email_id=:e"), {"e": email_id})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    status, has_sent_at = asyncio.run(scenario())
    assert status == "sent" and has_sent_at


def test_old_statement_fails_on_postgres_so_the_fix_is_real(monkeypatch):
    """The pre-fix SQL raises the exact production error."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _url(monkeypatch)

    async def scenario():
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE email_outbox SET status=:status,sent_at=CASE WHEN :status='sent' THEN NOW() ELSE sent_at END "
                    "WHERE email_id=:e"), {"status": "sent", "e": "none"})
        finally:
            await engine.dispose()

    with pytest.raises(Exception, match="inconsistent types"):
        asyncio.run(scenario())


def test_one_verification_email_per_ten_minutes_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _url(monkeypatch)
    tag = uuid4().hex[:8]

    async def scenario():
        from db.session import dispose_engine_for_event_loop, get_session
        from services.platform.identity import AuthenticationError, request_email_verification

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text(
                    "INSERT INTO users(username, created_at, tier, primary_email, auto_renew) "
                    "VALUES (:u, NOW(), 'free', :m, FALSE) RETURNING id"),
                    {"u": f"vs_{tag}", "m": f"vs_{tag}@example.invalid"})).scalar_one()
            outcomes = []
            for _ in range(3):
                async with get_session() as session:
                    try:
                        await request_email_verification(session, user_id=uid, base_url="https://example.invalid")
                        outcomes.append("queued")
                    except AuthenticationError as exc:
                        outcomes.append(str(exc))
                    await session.commit()
            async with engine.begin() as conn:
                count = (await conn.execute(text(
                    "SELECT COUNT(*) FROM email_outbox WHERE user_id=:u AND template='verify_email'"), {"u": uid})).scalar()
            return outcomes, count
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM email_outbox WHERE user_id IN (SELECT id FROM users WHERE username=:u)"),
                                   {"u": f"vs_{tag}"})
                await conn.execute(text("DELETE FROM login_challenges WHERE user_id IN "
                                        "(SELECT id FROM users WHERE username=:u)"), {"u": f"vs_{tag}"})
                await conn.execute(text("DELETE FROM users WHERE username=:u"), {"u": f"vs_{tag}"})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    outcomes, count = asyncio.run(scenario())
    assert outcomes == ["queued", "verification_recently_sent", "verification_recently_sent"]
    assert count == 1
