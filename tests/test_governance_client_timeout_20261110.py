"""10 Nov 2026 production: a client-side asyncpg timeout must not fail the whole review.

analytics 00:43–04:47 UTC: '[codex_governance] section=decision_log#1 failed after
45.3s error=TimeoutError', then every later section 'failed after 0.0s
error=PendingRollbackError' and '[continuous_improvement] scheduled review failed'
(10 times in 24 h). The asyncpg command_timeout invalidates the connection, so the
section savepoint cannot roll back on its own.
"""
from __future__ import annotations

import asyncio
import os

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


class _FakeSession:
    def __init__(self):
        self.rollbacks = 0
        self.invalid = False

    def begin_nested(self):
        session = self

        class _Nested:
            async def __aenter__(self):
                if session.invalid:
                    raise RuntimeError("PendingRollbackError")
                return self

            async def __aexit__(self, *exc):
                return False

        return _Nested()

    async def execute(self, statement, params=None):
        if "slow" in str(statement):
            self.invalid = True
            raise TimeoutError()

        class _R:
            def mappings(self):
                return self

            def all(self):
                return [{"n": 1}]

        return _R()

    async def rollback(self):
        self.rollbacks += 1
        self.invalid = False


def test_failed_section_rolls_back_so_the_next_section_runs():
    from services import codex_governance as cg

    session = _FakeSession()
    unavailable: list[str] = []

    async def run():
        first = await cg._guarded_execute(session, unavailable, "SELECT slow FROM decision_log")
        second = await cg._guarded_execute(session, unavailable, "SELECT n FROM signals")
        return first, second

    first, second = asyncio.run(run())
    assert first.all() == []
    assert second.all() == [{"n": 1}]
    assert unavailable == ["decision_log#1:TimeoutError"]
    assert session.rollbacks == 1


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_client_command_timeout_drops_only_the_slow_sections(monkeypatch):
    from db.session import _normalize_database_url

    monkeypatch.setenv("DATABASE_URL", _normalize_database_url(_PG_DSN, async_driver=True))
    monkeypatch.setenv("DB_COMMAND_TIMEOUT", "1")
    from services import codex_governance as cg

    real = cg._guarded_execute

    async def slow_decision_log(session, unavailable, statement, params=None):
        if "FROM decision_log" in str(getattr(statement, "text", statement)):
            from sqlalchemy import text

            # No server-side statement_timeout: the 1 s asyncpg command_timeout fires,
            # as the 45 s one does in production.
            statement = text("SELECT pg_sleep(3)")
        return await real(session, unavailable, statement, params)

    monkeypatch.setattr(cg, "_guarded_execute", slow_decision_log)

    async def run():
        from db.session import dispose_engine_for_event_loop

        try:
            return await cg.collect_codex_governance_context(days=7, limit=5)
        finally:
            await dispose_engine_for_event_loop()

    context = asyncio.run(run())
    assert context["ok"] is True
    failed = context["unavailable_sections"]
    assert failed, "the slow sections should be reported"
    assert not any("PendingRollbackError" in s for s in failed), failed
    # Only the two decision_log sections (replaced by pg_sleep) were slow;
    # every other section still ran on a fresh connection.
    assert len(failed) == 2 and all(s.endswith(":TimeoutError") for s in failed), failed
    assert context["summary"] is not None
