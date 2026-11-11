"""A referred user's first payment rewards both sides, once (owner request, 11 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_first_payment_rewards_referrer_and_new_customer_once(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    tag = uuid4().hex[:8]
    base_tg = 700000000 + int(tag[:6], 16) % 99999999

    async def scenario():
        from db.pg_features import record_referral_conversion
        from db.repository import activate_subscription
        from db.session import dispose_engine_for_event_loop, get_session

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                ref_id = (await conn.execute(text(
                    "INSERT INTO users(username, telegram_user_id, created_at, tier, auto_renew) "
                    "VALUES (:u, :tg, NOW(), 'free', FALSE) RETURNING id"), {"u": f"rr_{tag}", "tg": base_tg})).scalar_one()
                new_id = (await conn.execute(text(
                    "INSERT INTO users(username, telegram_user_id, created_at, tier, auto_renew) "
                    "VALUES (:u, :tg, NOW(), 'free', FALSE) RETURNING id"), {"u": f"rn_{tag}", "tg": base_tg + 1})).scalar_one()
                await conn.execute(text(
                    "INSERT INTO referrals(referred_user_id, referrer_user_id, created_at, is_successful, reward_applied) "
                    "VALUES (:n, :r, NOW(), FALSE, FALSE)"), {"n": new_id, "r": ref_id})
            async with get_session() as s:
                await activate_subscription(s, telegram_user_id=base_tg + 1, user_id=new_id, tier="premium",
                                            duration_days=30, paystack_reference=f"pay_{tag}", meta={})
                first = await record_referral_conversion(s, referred_telegram_user_id=base_tg + 1,
                                                         payment_reference=f"pay_{tag}")
                again = await record_referral_conversion(s, referred_telegram_user_id=base_tg + 1,
                                                         payment_reference=f"pay_{tag}")
                renewal = await record_referral_conversion(s, referred_telegram_user_id=base_tg + 1,
                                                           payment_reference=f"pay2_{tag}")
                await s.commit()
            async with engine.begin() as conn:
                kinds = dict((await conn.execute(text(
                    "SELECT reward_type, SUM(reward_value) FROM referral_rewards WHERE referred_user_id=:n "
                    "GROUP BY 1"), {"n": new_id})).all())
            return first, again, renewal, kinds
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM referral_rewards WHERE referred_user_id IN "
                                        "(SELECT id FROM users WHERE username LIKE :p)"), {"p": f"r%_{tag}"})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    first, again, renewal, kinds = asyncio.run(scenario())
    assert first["recorded"] and first["referrer_days"] == 14 and first["welcome_days"] == 5
    assert "subscribed" in first["referrer_message"]
    assert again.get("idempotent") is True
    assert "referrer_days" not in renewal and "welcome_days" not in renewal  # a renewal is not a first purchase
    assert kinds["conversion_days"] == 14 and kinds["welcome_days"] == 5
