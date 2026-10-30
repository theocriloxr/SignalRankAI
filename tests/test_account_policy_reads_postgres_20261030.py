"""Broker-account reads work on real PostgreSQL (30 Oct 2026).

get_account_policy, reconciliation_snapshot, list_account_ledger,
evaluate_persisted_account_policy and record_reconciliation read ORM rows after
``session.rollback()``, which expires them; on a real database every call
raised DetachedInstanceError whenever the row existed (the policy and ledger
endpoints returned errors and the execution admission check crashed). Tests
with in-memory fakes did not show it. Skipped without an isolated PostgreSQL;
required when SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1.
"""
from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql" and os.getenv("APP_ENV") == "test"
    assert parsed.host in {"127.0.0.1", "localhost"} and "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _prop_account() -> tuple[int, str]:
    from db.models import BrokerConnection
    from db.session import get_session
    from services.account_policies import configure_account_policy

    tag = uuid4().hex[:10]
    connection_id = f"prop-{tag}"
    async with get_session() as session:
        uid = (await session.execute(text(
            "INSERT INTO users(username, created_at, tier, primary_email, auto_renew) "
            "VALUES(:u, NOW(), 'premium', :e, FALSE) RETURNING id"), {"u": f"prop-{tag}", "e": f"prop-{tag}@example.test"})).scalar_one()
        session.add(BrokerConnection(connection_id=connection_id, user_id=uid, platform="mt5", connector="metaapi",
                                     account_ref="5550001", environment="demo", status="connected", meta={},
                                     permissions={}, capabilities={}, execution_enabled=False))
        await session.commit()
    await configure_account_policy(uid, connection_id, account_mode="PROP", execution_permission="MANUAL",
                                   max_daily_loss_pct="0.04", max_total_drawdown_pct="0.08",
                                   external_max_daily_loss_pct="0.05", external_max_total_drawdown_pct="0.10",
                                   safety_buffer_pct="0.01", prop_firm="Example Firm", prop_rules_version="2026-10",
                                   prop_phase="challenge")
    return uid, connection_id



@pytest.mark.asyncio
async def test_policy_reconciliation_ledger_and_admission_read_back(isolated_postgres):
    from core.account_policy import AccountRiskSnapshot
    from services import account_policies as ap
    from services.trading_account_ledger import append_account_ledger_entry, list_account_ledger

    uid, connection_id = await _prop_account()
    await append_account_ledger_entry(user_id=uid, connection_id=connection_id, provider="mt5",
                                      entry_type="equity_snapshot", source_event_id="reads-1", equity="100000")

    assert (await ap.record_reconciliation(uid, connection_id, status="HEALTHY"))["ready"] is True
    policy = await ap.get_account_policy(uid, connection_id)
    assert policy["account_mode"] == "PROP" and policy["prop_firm"] == "Example Firm"
    assert (await ap.reconciliation_snapshot(uid, connection_id))["status"] == "HEALTHY"
    ledger = await list_account_ledger(uid, connection_id)
    assert [(e["entry_type"], e["equity"]) for e in ledger] == [("equity_snapshot", "100000.0000000000")]
    decision = await ap.evaluate_persisted_account_policy(
        uid, connection_id,
        AccountRiskSnapshot(current_equity=Decimal("100000"), day_start_equity=Decimal("100000"),
                            peak_equity=Decimal("100000")),
        execution_mode="manual_confirmed")
    assert decision.policy_version == policy["policy_version"]  # a real decision, not a crash
    assert "account_policy_missing" not in decision.reasons
