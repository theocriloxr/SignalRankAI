"""Failed password sign-ins are limited per account, not per spoofable IP (29 Oct 2026 threat model).

The route limiter keys on the first X-Forwarded-For value, which a client can
rotate on every request. These tests rotate it and still hit the per-account
limit, against a real PostgreSQL schema (skipped without one; required when
SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from sqlalchemy import text
from sqlalchemy.engine import make_url
from starlette.requests import Request

PASSWORD = "Correct-Horse-Battery-29!"


@pytest_asyncio.fixture
async def isolated_postgres(monkeypatch):
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
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_ACCOUNT", "5")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


def _request(attempt: int) -> Request:
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/platform/auth/login", "query_string": b"",
        "scheme": "https", "server": ("test", 443), "client": ("127.0.0.1", 40000 + attempt),
        "headers": [(b"user-agent", b"pytest"), (b"x-forwarded-for", f"203.0.113.{attempt % 250}".encode())],
    })


async def _attempt(email: str, password: str, attempt: int) -> int:
    from web.platform_api import LoginRequest, login

    try:
        await login(LoginRequest(email=email, password=password), _request(attempt), Response())
    except HTTPException as exc:
        return exc.status_code
    return 200


async def _account() -> str:
    from db.session import get_session
    from services.platform.identity import create_email_account

    email = f"throttle-{uuid4().hex[:10]}@example.test"
    async with get_session() as session:
        uid = await create_email_account(session, email=email, password=PASSWORD, display_name="Throttle test")
        await session.execute(text("UPDATE users SET email_verified_at=NOW() WHERE id=:uid"), {"uid": uid})
        await session.commit()
    return email


@pytest.mark.asyncio
async def test_rotating_forwarded_addresses_does_not_bypass_the_account_limit(isolated_postgres):
    email = await _account()
    assert [await _attempt(email, "wrong-guess", i) for i in range(5)] == [401] * 5
    assert await _attempt(email, "wrong-guess", 5) == 429
    assert await _attempt(email.upper(), PASSWORD, 6) == 429  # even the right password, any address or case


@pytest.mark.asyncio
async def test_the_right_password_works_below_the_limit_and_failures_keep_counting(isolated_postgres):
    email = await _account()
    assert [await _attempt(email, "wrong-guess", i) for i in range(4)] == [401] * 4
    assert await _attempt(email, PASSWORD, 4) == 200
    assert await _attempt(email, "wrong-guess", 5) == 401  # fifth failure in the window locks
    assert await _attempt(email, PASSWORD, 6) == 429


@pytest.mark.asyncio
async def test_unknown_emails_lock_the_same_way(isolated_postgres):
    ghost = f"nobody-{uuid4().hex[:10]}@example.test"
    assert [await _attempt(ghost, "x", i) for i in range(5)] == [401] * 5
    assert await _attempt(ghost, "x", 5) == 429  # same behaviour: the lock reveals no account


def test_store_errors_fail_open(monkeypatch):
    from core.redis_state import state
    from services.platform import login_throttle

    def broken(*_args, **_kwargs):
        raise ConnectionError("store down")

    monkeypatch.setattr(state, "get_sync", broken)
    monkeypatch.setattr(state, "incr_sync", broken)
    assert login_throttle.is_locked("a@example.test") is False
    assert login_throttle.record_failure("a@example.test") == 0
