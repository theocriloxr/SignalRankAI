"""Reads that crashed or silently came back empty on real PostgreSQL (30 Oct 2026).

Two causes, both invisible to tests with in-memory fakes:

* rows read after ``session.rollback()``, which expires them
  (DetachedInstanceError once the session closes);
* time-zone-aware datetimes bound to ``timestamp without time zone`` columns,
  which asyncpg refuses (DataError), usually swallowed into an empty result.

Skipped without an isolated PostgreSQL; required when
SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: F401


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _user(tier: str = "free", *, subscribed: str | None = None, email: bool = False) -> tuple[int, int]:
    from db.models import Subscription, User
    from db.session import get_session

    telegram_id = 7_400_000_000 + int(uuid4().hex[:7], 16)
    async with get_session() as session:
        user = User(telegram_user_id=telegram_id, username=f"regress-{telegram_id}", tier=tier, timezone="UTC",
                    primary_email=f"regress-{telegram_id}@example.test" if email else None,
                    email_verified_at=_naive_now() if email else None)
        session.add(user)
        await session.flush()
        if subscribed:
            session.add(Subscription(user_id=user.id, tier=subscribed, status="active",
                                     expires_at=_naive_now() + timedelta(days=30)))
        await session.commit()
        return int(user.id), telegram_id


def _update(telegram_id: int, replies: list[str]):
    async def reply_text(message, **kwargs):
        replies.append(str(message))

    chat = SimpleNamespace(type="private", id=telegram_id)
    return SimpleNamespace(message=SimpleNamespace(reply_text=reply_text, chat=chat), effective_chat=chat,
                           effective_user=SimpleNamespace(id=telegram_id, username=None, first_name="Test"))


@pytest.mark.asyncio
async def test_verifybroker_reaches_the_connection_lookup(postgres_database):  # noqa: F811
    from signalrank_telegram.commands import verifybroker_command

    _, telegram_id = await _user("premium", subscribed="premium")
    replies: list[str] = []
    await verifybroker_command(_update(telegram_id, replies), SimpleNamespace(args=[]))
    assert replies and replies[-1].startswith("No matching MT4/MT5/Bybit account is connected"), replies


@pytest.mark.asyncio
async def test_legacy_bybit_credentials_load(postgres_database, monkeypatch):  # noqa: F811
    from cryptography.fernet import Fernet

    from db.models import RuntimeState
    from db.session import get_session
    from services import bybit_reconciler
    from services.security import encrypt_secret

    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    user_id, telegram_id = await _user()
    async with get_session() as session:
        session.add(RuntimeState(key=bybit_reconciler._state_key(telegram_id), updated_at=_naive_now(),
                                 value={"api_key_enc": encrypt_secret("demo-key"),
                                        "api_secret_enc": encrypt_secret("demo-secret"), "sandbox": True}))
        await session.commit()
    credentials = await bybit_reconciler._credentials(user_id, telegram_id, None)
    assert credentials is not None and credentials.api_key == "demo-key" and credentials.testnet is True


@pytest.mark.asyncio
async def test_legacy_checkout_passes_the_account(postgres_database, monkeypatch):  # noqa: F811
    import payments.checkout as checkout
    from db.session import get_session
    from web.app import PaystackCheckoutRequest, paystack_charge_create

    user_id, telegram_id = await _user(email=True)
    product_id = f"regress-{uuid4().hex[:8]}"
    async with get_session() as session:
        await session.execute(text("INSERT INTO subscription_products(product_id,tier,display_name,duration_days) "
                                   "VALUES(:p,'premium','Regression premium',30)"), {"p": product_id})
        await session.execute(text("INSERT INTO subscription_prices(product_id,currency,price_kobo,effective_from) "
                                   "VALUES(:p,'NGN',500000,NOW() - INTERVAL '1 minute')"), {"p": product_id})
        await session.commit()
    seen: dict = {}

    async def no_paystack(**kwargs):  # the Paystack API is the only network edge
        seen.update(kwargs)
        return {"authorization_url": "https://checkout.example.test/regress"}

    monkeypatch.setattr(checkout, "initialize_paystack_checkout", no_paystack)
    result = await paystack_charge_create(PaystackCheckoutRequest(product_id=product_id), telegram_id)
    assert result["authorization_url"].startswith("https://checkout.example.test/")
    assert seen["canonical_user_id"] == user_id and seen["email"] == f"regress-{telegram_id}@example.test"


@pytest.mark.asyncio
async def test_owner_and_admin_reports_count_recent_rows(postgres_database, monkeypatch):  # noqa: F811
    from db.models import Signal
    from db.session import get_session
    from signalrank_telegram import admin_commands, commands, owner_commands

    _, owner_id = await _user()
    await _user(subscribed="vip")
    strategy = f"regress-{uuid4().hex[:6]}"
    async with get_session() as session:
        session.add(Signal(signal_id=str(uuid4()), asset="REGRESSUSDT", timeframe="1h", direction="long", entry=1.0,
                           stop_loss=0.9, take_profit="[1.2]", score=80, strategy_name=strategy,
                           strategy_group=strategy, strength=1, created_at=_naive_now()))
        await session.commit()

    async def allowed(_user_id):
        return True

    monkeypatch.setattr(owner_commands, "_is_strict_owner", allowed)
    monkeypatch.setattr(admin_commands, "_is_admin", lambda _uid: True)
    monkeypatch.setattr(commands, "_is_admin", lambda _uid: True)
    replies: list[str] = []
    await owner_commands.owner_users(_update(owner_id, replies), SimpleNamespace(args=[]))
    assert replies and "Unable to load" not in replies[-1] and "vip" in replies[-1].lower(), replies
    for module in (admin_commands, commands):
        replies.clear()
        await module.admin_top_strategies_command(_update(owner_id, replies), SimpleNamespace(args=[]))
        assert replies and strategy in replies[-1], (module.__name__, replies)


@pytest.mark.asyncio
async def test_cached_calendar_events_are_readable_by_the_news_gate(postgres_database):  # noqa: F811
    from db.models import EconomicEvent
    from db.session import get_session
    from worker.news_sync_worker import get_cached_high_impact_events

    title = f"Regression release {uuid4().hex[:6]}"
    when = _naive_now().replace(microsecond=0) + timedelta(hours=2)
    async with get_session() as session:
        session.add(EconomicEvent(event_date=when, currency="USD", title=title, impact="high", source="test",
                                  fetched_at=_naive_now()))
        await session.commit()
    events = [e for e in await get_cached_high_impact_events(hours=6) if e["title"] == title]
    assert len(events) == 1
    assert events[0]["event_time"] == when.replace(tzinfo=timezone.utc)  # key the news gate reads
