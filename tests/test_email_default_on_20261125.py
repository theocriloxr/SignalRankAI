"""Email notifications default on for verified users who never chose (25 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest


def test_new_preference_rows_default_email_on():
    assert "VALUES(:uid,FALSE,TRUE)" in Path("services/platform/identity.py").read_text()
    api = Path("web/platform_api.py").read_text()
    assert "'email_choice'" in api and "VALUES(:uid, TRUE) ON CONFLICT" in api


def test_backfill_switches_on_only_undecided_verified_users(monkeypatch):
    dsn = os.getenv("SIGNALRANK_TEST_PG_DSN")
    if not dsn:
        pytest.skip("needs SIGNALRANK_TEST_PG_DSN")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from services import post_deploy_maintenance as pdm

    url = _normalize_database_url(dsn, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)

    async def scenario():
        from db.session import dispose_engine_for_event_loop

        engine = create_async_engine(url)
        ids: dict[str, int] = {}
        try:
            async with engine.begin() as conn:
                for name, verified, prefs in (("undecided", True, "{}"), ("chose_off", True, '{"email_choice":"off"}'),
                                              ("unverified", False, "{}")):
                    ids[name] = (await conn.execute(text(
                        "INSERT INTO users (created_at, tier, primary_email, email_verified_at) VALUES "
                        "(NOW(), 'free', :e, CASE WHEN :v THEN NOW() ELSE NULL END) RETURNING id"),
                        {"e": f"{name}.default-on@example.com", "v": verified})).scalar_one()
                    await conn.execute(text("INSERT INTO notification_preferences(user_id, email_enabled, preferences) "
                                            "VALUES (:u, FALSE, CAST(:p AS JSONB))"), {"u": ids[name], "p": prefs})
            await pdm.enable_email_for_undecided_users()
            await pdm.enable_email_for_undecided_users()  # idempotent
            async with engine.connect() as conn:
                state = {name: (await conn.execute(text(
                    "SELECT email_enabled FROM notification_preferences WHERE user_id=:u"), {"u": uid})).scalar_one()
                    for name, uid in ids.items()}
            assert state == {"undecided": True, "chose_off": False, "unverified": False}
        finally:
            async with engine.begin() as conn:
                for uid in ids.values():
                    await conn.execute(text("DELETE FROM notification_preferences WHERE user_id=:u"), {"u": uid})
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    asyncio.run(scenario())
