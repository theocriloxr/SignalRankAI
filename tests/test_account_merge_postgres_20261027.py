"""Telegram <-> web account merge keeps every user's data (27 Oct 2026).

A web account that links a Telegram identity which already has a bot account
used to stop at ``merge_review`` forever: nothing completed the review, so the
bot subscription, paper trading, watchlists and preferences stayed on another
account. These tests drive the real link flow and the reviewed merge against a
real PostgreSQL schema. They skip without an isolated local PostgreSQL and fail
when SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.asyncio


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
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _scenario(web_has_paper: bool) -> dict:
    """A web account and a separate legacy bot account for the same person."""
    from db.session import get_session
    from services.platform.identity import complete_telegram_link_request, create_telegram_link_request

    tag = uuid4().hex[:10]
    telegram_id = random.randint(10**9, 2 * 10**9)
    now = datetime.utcnow()
    async with get_session() as session:
        web = (await session.execute(text(
            "INSERT INTO users(username, created_at, tier, primary_email, auto_renew) "
            "VALUES(:u, NOW(), 'free', :email, FALSE) RETURNING id"
        ), {"u": f"web-{tag}", "email": f"merge-{tag}@example.test"})).scalar_one()
        bot = (await session.execute(text(
            "INSERT INTO users(username, telegram_user_id, created_at, tier, premium_until, auto_renew, "
            "paystack_subscription_code, timezone) VALUES(:u, :tg, NOW(), 'premium', :until, TRUE, :sub, 'Africa/Lagos') "
            "RETURNING id"
        ), {"u": f"bot-{tag}", "tg": telegram_id, "until": now + timedelta(days=20), "sub": f"SUB_{tag}"})).scalar_one()
        # Bot history: watchlists (one name collides), alerts preferences, journal, paper trading, a session.
        for owner, name in ((bot, "Majors"), (bot, "Gold"), (web, "Majors")):
            await session.execute(text(
                "INSERT INTO watchlists(watchlist_id, user_id, name) VALUES(:id, :uid, :name)"
            ), {"id": str(uuid4()), "uid": owner, "name": name})
        for owner in (bot, web):
            await session.execute(text("INSERT INTO notification_preferences(user_id) VALUES(:uid)"), {"uid": owner})
        await session.execute(text(
            "INSERT INTO journal_entries(journal_entry_id, user_id) VALUES(:id, :uid)"
        ), {"id": str(uuid4()), "uid": bot})
        signal_id = f"merge-sig-{tag}"
        await session.execute(text(
            "INSERT INTO signals(signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, score, "
            "strategy_name, strategy_group, strength, created_at, display_id) VALUES(:sid, 'BTCUSDT', '1h', 'long', "
            "100, 95, '110', 80, 'breakout', 'trend', 1, NOW(), :display)"
        ), {"sid": signal_id, "display": tag[:8]})
        bot_account = (await session.execute(text(
            "INSERT INTO paper_accounts(user_id) VALUES(:uid) RETURNING id"), {"uid": bot})).scalar_one()
        if web_has_paper:
            await session.execute(text("INSERT INTO paper_accounts(user_id) VALUES(:uid)"), {"uid": web})
        await session.execute(text(
            "INSERT INTO paper_positions(position_id, account_id, user_id, signal_id, asset, direction, signal_entry, "
            "fill_entry, current_price, stop_loss) VALUES(:pid, :acc, :uid, :sid, 'BTCUSDT', 'long', 100, 100, 101, 95)"
        ), {"pid": str(uuid4()), "acc": bot_account, "uid": bot, "sid": signal_id})
        await session.execute(text(
            "INSERT INTO paper_ledger_entries(account_id, user_id, entry_type, balance_after) "
            "VALUES(:acc, :uid, 'deposit', 10000)"
        ), {"acc": bot_account, "uid": bot})
        await session.execute(text(
            "INSERT INTO user_sessions(session_id, user_id, refresh_token_hash, session_family_id, expires_at) "
            "VALUES(:sid, :uid, :hash, :fam, :exp)"
        ), {"sid": str(uuid4()), "uid": bot, "hash": uuid4().hex, "fam": str(uuid4()), "exp": now + timedelta(days=1)})
        request = await create_telegram_link_request(session, user_id=web)
        result = await complete_telegram_link_request(session, token_or_code=request.code, telegram_user_id=telegram_id)
        await session.commit()
    assert result.status == "merge_review_required"
    return {"web": web, "bot": bot, "telegram_id": telegram_id, "merge_id": result.merge_id,
            "bot_paper_account": bot_account}


async def _count(session, sql: str, **params) -> int:
    return int((await session.execute(text(sql), params)).scalar_one())


async def test_preview_is_read_only_and_lists_what_would_move(isolated_postgres):
    from db.session import get_session
    from services.platform.account_merge import plan_account_merge

    s = await _scenario(web_has_paper=False)
    async with get_session() as session:
        plan = await plan_account_merge(session, s["merge_id"])
        await session.rollback()
        assert plan["movable"]["watchlists.user_id"] == 2
        assert plan["movable"]["paper_positions.user_id"] == 1
        assert plan["never_moved"]["user_sessions.user_id"] == 1
        assert plan["account_changes"]["tier"] == "premium"
        assert await _count(session, "SELECT COUNT(*) FROM watchlists WHERE user_id=:u", u=s["bot"]) == 2
        status = (await session.execute(text("SELECT status FROM account_merge_records WHERE merge_id=:m"),
                                        {"m": s["merge_id"]})).scalar_one()
        assert status == "pending_review"


async def test_apply_moves_history_keeps_conflicts_and_links_telegram(isolated_postgres):
    from db.session import get_session
    from services.platform.account_merge import MergeRefused, apply_account_merge
    from services.platform.identity import user_snapshot

    s = await _scenario(web_has_paper=False)
    async with get_session() as session:
        evidence = await apply_account_merge(session, s["merge_id"], reviewer_user_id=s["web"])
        await session.commit()

    async with get_session() as session:
        web = (await session.execute(text(
            "SELECT telegram_user_id, tier, premium_until, paystack_subscription_code, auto_renew, timezone "
            "FROM users WHERE id=:u"), {"u": s["web"]})).mappings().one()
        bot = (await session.execute(text(
            "SELECT telegram_user_id, account_status FROM users WHERE id=:u"), {"u": s["bot"]})).mappings().one()
        assert web["telegram_user_id"] == s["telegram_id"] and bot["telegram_user_id"] is None
        assert bot["account_status"] == "merged"
        # Paid access and its renewal choice follow the person; empty profile fields are filled.
        assert web["tier"] == "premium" and web["premium_until"] is not None
        assert web["paystack_subscription_code"].startswith("SUB_") and web["auto_renew"] is True
        assert web["timezone"] == "Africa/Lagos"
        # Non-colliding history moved; the colliding "Majors" watchlist stays on the archived account.
        names = sorted(r[0] for r in (await session.execute(
            text("SELECT name FROM watchlists WHERE user_id=:u"), {"u": s["web"]})).all())
        assert names == ["Gold", "Majors"]
        assert await _count(session, "SELECT COUNT(*) FROM watchlists WHERE user_id=:u", u=s["bot"]) == 1
        assert evidence["kept_on_archived_account"]["watchlists.user_id"] == 1
        # One-per-account preferences: the kept account's row wins, the other is retained, not deleted.
        assert await _count(session, "SELECT COUNT(*) FROM notification_preferences WHERE user_id=:u", u=s["bot"]) == 1
        # Paper trading moves as one family: account, positions and ledger together.
        assert await _count(session, "SELECT COUNT(*) FROM paper_accounts WHERE user_id=:u", u=s["web"]) == 1
        assert await _count(session, "SELECT COUNT(*) FROM paper_positions WHERE user_id=:u AND account_id=:a",
                            u=s["web"], a=s["bot_paper_account"]) == 1
        assert await _count(session, "SELECT COUNT(*) FROM paper_ledger_entries WHERE user_id=:u", u=s["web"]) == 1
        assert await _count(session, "SELECT COUNT(*) FROM paper_positions p JOIN paper_accounts a ON a.id=p.account_id "
                            "WHERE p.user_id<>a.user_id AND p.user_id IN (:w, :b)", w=s["web"], b=s["bot"]) == 0
        assert await _count(session, "SELECT COUNT(*) FROM journal_entries WHERE user_id=:u", u=s["web"]) == 1
        # Credentials never move; the archived account's sessions are revoked.
        assert await _count(session, "SELECT COUNT(*) FROM user_sessions WHERE user_id=:u AND revoked_at IS NULL",
                            u=s["bot"]) == 0
        assert evidence["never_moved"]["user_sessions.user_id"] == 1
        snapshot = await user_snapshot(session, s["web"])
        assert snapshot["telegram_link_status"] == "linked"
        assert (await session.execute(text("SELECT status FROM account_merge_records WHERE merge_id=:m"),
                                      {"m": s["merge_id"]})).scalar_one() == "completed"
        with pytest.raises(MergeRefused):
            await apply_account_merge(session, s["merge_id"], reviewer_user_id=s["web"])
        await session.rollback()


async def test_paper_family_stays_together_when_the_web_account_already_has_one(isolated_postgres):
    from db.session import get_session
    from services.platform.account_merge import apply_account_merge

    s = await _scenario(web_has_paper=True)
    async with get_session() as session:
        evidence = await apply_account_merge(session, s["merge_id"], reviewer_user_id=s["web"])
        await session.commit()
    async with get_session() as session:
        # The bot's paper account cannot move (one per account), so its positions and
        # ledger stay with it instead of pointing at an account the user no longer owns.
        assert await _count(session, "SELECT COUNT(*) FROM paper_accounts WHERE user_id=:u", u=s["bot"]) == 1
        assert await _count(session, "SELECT COUNT(*) FROM paper_positions WHERE user_id=:u", u=s["bot"]) == 1
        assert await _count(session, "SELECT COUNT(*) FROM paper_ledger_entries WHERE user_id=:u", u=s["bot"]) == 1
        mismatched = await _count(session,
            "SELECT COUNT(*) FROM paper_positions p JOIN paper_accounts a ON a.id=p.account_id "
            "WHERE p.user_id<>a.user_id AND p.user_id IN (:w, :b)", w=s["web"], b=s["bot"])
        assert mismatched == 0
        assert evidence["kept_on_archived_account"]["paper_accounts.user_id"] == 1
        assert evidence["kept_on_archived_account"]["paper_positions.user_id"] == 1


async def test_partial_unique_collision_keeps_only_the_colliding_row(isolated_postgres):
    from db.session import get_session
    from services.platform.account_merge import _move_rows_individually, _move_sql

    async with get_session() as session:
        await session.execute(text(
            "CREATE TEMP TABLE merge_probe(id SERIAL PRIMARY KEY, user_id INT NOT NULL, asset TEXT, status TEXT)"))
        await session.execute(text(
            "CREATE UNIQUE INDEX merge_probe_open ON merge_probe(user_id, upper(asset)) WHERE status = 'open'"))
        await session.execute(text(
            "INSERT INTO merge_probe(user_id, asset, status) VALUES "
            "(1, 'BTCUSDT', 'open'), (2, 'BTCUSDT', 'open'), (2, 'ETHUSDT', 'open'), (2, 'BTCUSDT', 'closed')"))
        sql = _move_sql("merge_probe", "user_id", [], [], [(["user_id", "asset"], False)], {})
        params = {"merged": 2, "canonical": 1}
        nested = await session.begin_nested()
        with pytest.raises(Exception):
            await session.execute(text(sql), params)
        await nested.rollback()
        assert await _move_rows_individually(session, sql, params) == 2
        left = (await session.execute(text("SELECT asset, status FROM merge_probe WHERE user_id = 2"))).all()
        assert [tuple(r) for r in left] == [("BTCUSDT", "open")]
        await session.rollback()


async def test_operator_endpoints_preview_and_apply_with_owner_safeguards(isolated_postgres, monkeypatch):
    from fastapi import HTTPException

    import web.platform_api as platform_api

    s = await _scenario(web_has_paper=False)
    owner = {"id": s["web"], "auth_age_seconds": 30.0}
    monkeypatch.setattr(platform_api, "_platform_operator_authority", lambda _user: "OWNER")
    listing = await platform_api.operator_account_merges(user=owner)
    assert s["merge_id"] in {row["merge_id"] for row in listing["pending"]}
    preview = await platform_api.operator_account_merge_preview(s["merge_id"], user=owner)
    assert preview["plan"]["movable"]["watchlists.user_id"] == 2

    request = platform_api.OperatorAccountMergeRequest
    for payload, user, status in (
        (request(confirm=False, confirm_merge_id=s["merge_id"]), owner, 422),
        (request(confirm=True, confirm_merge_id="0" * 36), owner, 422),
        (request(confirm=True, confirm_merge_id=s["merge_id"]), {**owner, "auth_age_seconds": 99_999}, 403),
    ):
        with pytest.raises(HTTPException) as exc:
            await platform_api.operator_account_merge_apply(s["merge_id"], payload, user=user)
        assert exc.value.status_code == status
    monkeypatch.setattr(platform_api, "_platform_operator_authority", lambda _user: "ADMIN")
    with pytest.raises(HTTPException) as exc:
        await platform_api.operator_account_merge_apply(
            s["merge_id"], request(confirm=True, confirm_merge_id=s["merge_id"]), user=owner)
    assert exc.value.status_code == 403

    monkeypatch.setattr(platform_api, "_platform_operator_authority", lambda _user: "OWNER")
    result = await platform_api.operator_account_merge_apply(
        s["merge_id"], request(confirm=True, confirm_merge_id=s["merge_id"]), user=owner)
    assert result["merge"]["movable"]["watchlists.user_id"] == 1
    with pytest.raises(HTTPException) as exc:
        await platform_api.operator_account_merge_preview(s["merge_id"], user=owner)
    assert exc.value.status_code == 409
