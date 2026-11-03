"""Production 2 Nov 2026: two account emails stayed in 'sending' for 16 h.

The claim set status='sending' and nothing ever reclaimed a row whose worker
stopped or whose status update failed after SMTP.  The batch now reclaims rows
past EMAIL_SENDING_LEASE_SECONDS (retry while the link is still valid, failed
otherwise) and a failed status update no longer aborts the rest of the batch.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import pytest

import services.platform.email_delivery as ed


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


def _install_fake_db(monkeypatch, claimed_rows, *, fail_update_for=()):
    statements: list[tuple[str, dict]] = []

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            statements.append((sql, dict(params or {})))
            if sql.startswith("UPDATE email_outbox SET status=:status") and params["email_id"] in fail_update_for:
                raise TimeoutError("db admission timeout")
            if "WITH claimed AS" in sql:
                return _Result(claimed_rows)
            return _Result([])

        async def commit(self):
            return None

    @asynccontextmanager
    async def _get_session():
        yield _Session()

    monkeypatch.setattr(ed, "get_session", _get_session)
    monkeypatch.setattr(ed, "is_db_configured", lambda: True)
    monkeypatch.setattr(ed, "_smtp_configured", lambda: True)
    return statements


def _row(email_id):
    return {"email_id": email_id, "recipient": "u@example.com", "subject": "s", "plain_body": "b",
            "html_body": None, "attempt_count": 1}


def test_stale_sending_rows_are_reclaimed_before_the_claim(monkeypatch):
    statements = _install_fake_db(monkeypatch, [])
    monkeypatch.setenv("EMAIL_SENDING_LEASE_SECONDS", "600")
    asyncio.run(ed.deliver_email_outbox_batch())
    assert statements[0][0] == ed._RECLAIM_STALE_SENDING_SQL
    assert statements[0][1] == {"lease": 600}
    assert "WITH claimed AS" in statements[1][0]


def test_lease_is_bounded(monkeypatch):
    monkeypatch.setenv("EMAIL_SENDING_LEASE_SECONDS", "5")
    assert ed._sending_lease_seconds() == 60
    monkeypatch.setenv("EMAIL_SENDING_LEASE_SECONDS", "not-a-number")
    assert ed._sending_lease_seconds() == 300
    monkeypatch.delenv("EMAIL_SENDING_LEASE_SECONDS")
    assert ed._sending_lease_seconds() == 300


def test_failed_status_update_does_not_strand_the_rest_of_the_batch(monkeypatch):
    statements = _install_fake_db(monkeypatch, [_row("a"), _row("b")], fail_update_for={"a"})
    sent: list[str] = []
    monkeypatch.setattr(ed, "_send_smtp", lambda row: sent.append(row["email_id"]))
    result = asyncio.run(ed.deliver_email_outbox_batch())
    assert sent == ["a", "b"]
    assert result["claimed"] == 2 and result["sent"] == 2
    updates = [p for sql, p in statements if sql.startswith("UPDATE email_outbox SET status=:status")]
    assert [p["email_id"] for p in updates] == ["a", "b"]
    assert updates[1]["status"] == "sent"


_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL")
def test_reclaim_sql_on_postgresql():
    asyncpg = pytest.importorskip("asyncpg")

    async def _run():
        conn = await asyncpg.connect(_PG_DSN)
        try:
            await conn.execute(
                "CREATE TEMP TABLE email_outbox (email_id text primary key, status text, context jsonb, "
                "last_error text, created_at timestamp, updated_at timestamp, next_attempt_at timestamp)"
            )
            rows = [
                # id, status, context, created (min ago), updated (min ago)
                ("expired_link", "sending", '{"expires_minutes": 15}', 16 * 60, 16 * 60),  # production case
                ("valid_link", "sending", '{"expires_minutes": 30}', 8, 8),
                ("within_lease", "sending", '{"expires_minutes": 15}', 2, 2),
                ("bad_context", "sending", '{"expires_minutes": "soon"}', 20, 20),
                ("already_sent", "sent", '{}', 60, 60),
            ]
            for email_id, status, ctx, created, updated in rows:
                await conn.execute(
                    "INSERT INTO email_outbox VALUES ($1,$2,$3::jsonb,NULL,"
                    "(NOW() AT TIME ZONE current_setting('TimeZone')) - make_interval(mins => $4),"
                    "(NOW() AT TIME ZONE current_setting('TimeZone')) - make_interval(mins => $5),"
                    "(NOW() AT TIME ZONE current_setting('TimeZone')) - make_interval(mins => $4))",
                    email_id, status, ctx, created, updated,
                )
            sql = ed._RECLAIM_STALE_SENDING_SQL.replace(":lease", "$1")
            await conn.execute(sql, 300)
            got = {r["email_id"]: (r["status"], r["last_error"])
                   for r in await conn.fetch("SELECT email_id, status, last_error FROM email_outbox")}
        finally:
            await conn.close()
        return got

    got = asyncio.run(_run())
    assert got["expired_link"] == ("failed", "sending_lease_expired")
    assert got["valid_link"] == ("retry", "sending_lease_expired")
    assert got["within_lease"] == ("sending", None)
    assert got["bad_context"] == ("failed", "sending_lease_expired")
    assert got["already_sent"] == ("sent", None)
