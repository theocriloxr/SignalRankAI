"""Fixes from the 9 Nov 2026 production log snapshot (signalrank-ops 07:45 UTC)."""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_one_slow_section_no_longer_fails_the_weekly_review(monkeypatch):
    """analytics 07:02:46: '[continuous_improvement] scheduled review failed' on an asyncpg TimeoutError."""
    from db.session import _normalize_database_url

    monkeypatch.setenv("DATABASE_URL", _normalize_database_url(_PG_DSN, async_driver=True))
    from services import codex_governance as cg

    real = cg._guarded_execute

    async def slow_decision_log(session, unavailable, statement, params=None):
        if "FROM decision_log" in str(getattr(statement, "text", statement)):
            from sqlalchemy import text

            # Simulate the production timeout inside the section's savepoint.
            statement = text("SELECT pg_sleep(3)")
            await session.execute(text("SET LOCAL statement_timeout = '200ms'"))
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
    # The two decision_log sections (latest decisions, AI provider performance) timed out.
    assert len(context["unavailable_sections"]) == 2
    assert all(s.endswith(":DBAPIError") for s in context["unavailable_sections"])
    assert "summary" in context  # the other sections still ran after the failed one


def test_scanner_server_action_requests_are_answered_by_the_proxy():
    """web 8 Nov: 'Failed to find Server Action' x24 in one second; the app has no Server Actions."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "frontend" / "src"
    proxy = (root / "proxy.ts").read_text("utf-8")
    assert 'request.headers.has("next-action")' in proxy and "status: 404" in proxy
    assert not any("use server" in p.read_text("utf-8", errors="ignore")
                   for p in root.rglob("*.ts*")), "a real Server Action now exists; revisit the proxy rule"
