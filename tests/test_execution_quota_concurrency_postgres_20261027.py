"""CX-RISK-03: simultaneous executions cannot jointly exceed a user's limit.

``services.execution_quota`` checks and increments the shared daily execution
counter under a ``SELECT ... FOR UPDATE`` row lock. This races many concurrent
reservations, each in its own database session, against a real PostgreSQL row.
Without the lock, several reservations read the same count and all pass.
Skips without an isolated local PostgreSQL; fails when
SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.asyncio

ATTEMPTS = 12


@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session
    from sqlalchemy import text

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql", "SQLite has no row locks to certify"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}, "integration mutations require a local isolated database"
    assert "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _premium_user() -> int:
    from db.models import User
    from db.session import get_session

    async with get_session() as session:
        user = User(username=f"quota-race-{uuid4().hex[:12]}", tier="premium", daily_executions_today=0)
        session.add(user)
        await session.commit()
        return int(user.id)


async def _counter(user_id: int) -> int:
    from db.models import User
    from db.session import get_session

    async with get_session() as session:
        return int((await session.get(User, user_id)).daily_executions_today or 0)


async def test_concurrent_reservations_never_exceed_the_daily_limit(isolated_postgres, monkeypatch):
    from services.execution_quota import reserve_platform_user_execution_quota

    monkeypatch.setenv("PREMIUM_DAILY_EXECUTIONS", "3")
    user_id = await _premium_user()

    results = await asyncio.gather(*(
        reserve_platform_user_execution_quota(user_id, tier="premium", execution_mode="manual")
        for _ in range(ATTEMPTS)
    ))

    approved = [r for r in results if r[0]]
    refused = [r for r in results if not r[0]]
    assert len(approved) == 3, results
    assert {r[1] for r in refused} == {"premium_daily_execution_limit"}, results
    assert await _counter(user_id) == 3


async def test_release_then_concurrent_reserve_keeps_the_ledger_exact(isolated_postgres, monkeypatch):
    from services.execution_quota import release_user_execution_quota, reserve_platform_user_execution_quota

    monkeypatch.setenv("PREMIUM_DAILY_EXECUTIONS", "2")
    user_id = await _premium_user()
    first = await asyncio.gather(*(
        reserve_platform_user_execution_quota(user_id, tier="premium", execution_mode="manual") for _ in range(4)
    ))
    assert sum(1 for r in first if r[0]) == 2

    # A definite pre-order rejection gives one slot back while others race for it.
    racers = [reserve_platform_user_execution_quota(user_id, tier="premium", execution_mode="manual")
              for _ in range(5)]
    outcome = await asyncio.gather(release_user_execution_quota(user_id), *racers)
    assert sum(1 for r in outcome[1:] if r[0]) <= 1
    assert await _counter(user_id) == 2
