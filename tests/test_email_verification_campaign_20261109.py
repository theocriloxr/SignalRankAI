"""Email verification for new and existing users (owner request, 9 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")
ROOT = Path(__file__).resolve().parents[1]


def test_every_signup_path_asks_for_verification():
    source = (ROOT / "web" / "platform_api.py").read_text("utf-8")
    start = source.index('@router.post("/auth/telegram/complete")')
    block = source[start:start + 6000]
    assert "_request_verification_quietly(session, int(user_id)" in block


def test_app_shows_a_verify_banner_until_verified():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text("utf-8")
    banner = (ROOT / "frontend" / "src" / "components" / "EmailVerifyBanner.tsx").read_text("utf-8")
    assert "<EmailVerifyBanner/>" in shell
    assert "email_verified_at" in banner and "/api/v1/platform/auth/email-verification/request" in banner


def test_owner_command_is_registered_for_owners_only():
    from core.tier_policy import COMMAND_MINIMUM_TIER, Tier

    assert COMMAND_MINIMUM_TIER.get("verify_email_campaign") == Tier.OWNER


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_campaign_counts_then_queues_and_skips_recently_asked(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    email = f"unverified-{uuid4().hex[:8]}@example.com"

    async def scenario():
        from db.session import dispose_engine_for_event_loop, get_session
        from services.platform.email_verification_campaign import run_campaign

        engine = create_async_engine(url)
        uid = None
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text(
                    "INSERT INTO users (created_at, tier, primary_email, telegram_user_id) VALUES "
                    "(NOW(), 'free', :e, :t) RETURNING id"), {"e": email, "t": 970_000_000 + int(uuid4().int % 1000)})).scalar_one()
            async with get_session() as session:
                dry = await run_campaign(session, base_url="https://example.test", send=False)
            async with get_session() as session:
                sent = await run_campaign(session, base_url="https://example.test", send=True)
            async with get_session() as session:
                again = await run_campaign(session, base_url="https://example.test", send=False)
            async with engine.connect() as conn:
                queued = (await conn.execute(text(
                    "SELECT COUNT(*) FROM email_outbox WHERE idempotency_key LIKE :k"), {"k": f"verify-email:{uid}:%"})).scalar()
            return uid, dry, sent, again, queued
        finally:
            async with engine.begin() as conn:
                if uid is not None:
                    for sql in ("DELETE FROM email_outbox WHERE idempotency_key LIKE :k",):
                        await conn.execute(text(sql), {"k": f"verify-email:{uid}:%"})
                    for table in ("account_challenges", "security_events"):
                        try:
                            async with conn.begin_nested():
                                await conn.execute(text(f"DELETE FROM {table} WHERE user_id=:u"), {"u": uid})
                        except Exception:
                            pass
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    uid, dry, sent, again, queued = asyncio.run(scenario())
    assert dry["eligible"] >= 1 and dry["queued"] == 0
    assert sent["queued"] >= 1 and queued == 1
    assert uid not in [u for u in again.get("telegram_ids", [])]
    assert again["eligible"] == dry["eligible"] - sent["queued"]  # asked within 24 h -> skipped
