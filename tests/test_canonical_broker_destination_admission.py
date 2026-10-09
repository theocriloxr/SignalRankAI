"""Destination admission rejects ambiguous or unknown broker ownership.

No real credentials, funds, live order placement or external account are used.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.broker_routing_policy import (
    destination_choice_allowed,
    enforce_canonical_destination,
)


@pytest.mark.parametrize(
    ("eligible", "expected"),
    [
        (None, "canonical_account_ownership_unresolved"),
        (0, "no_verified_execution_eligible_account"),
        (1, "one_canonical_execution_eligible_account"),
        (2, "explicit_connection_required_multi_account"),
        (3, "explicit_connection_required_multi_account"),
    ],
)
def test_missing_and_multiple_destinations_are_fail_closed(eligible, expected):
    ok, reason = destination_choice_allowed(explicit_connection=False, canonical_eligible_accounts=eligible)
    assert ok is (eligible == 1)
    assert reason == expected


def test_explicit_connection_cannot_gain_privileges_from_this_guard():
    allowed, reason = destination_choice_allowed(explicit_connection=True, canonical_eligible_accounts=None)
    assert allowed is True
    assert reason == "explicit_connection_selected"
    # Adapter-side owner, prop, risk and execution permission checks still apply;
    # this guard is not permission to trade.


@pytest.mark.asyncio
async def test_connection_count_enforces_exact_owner_with_two_accounts(monkeypatch):
    import services.broker_routing_policy as policy

    class FirstResult:
        def scalar_one_or_none(self):
            return 31

    class SecondResult:
        def scalars(self):
            return self

        def all(self):
            return ["account-1", "account-2"]

    class FakeSession:
        def __init__(self):
            self.commands = []
            self.rollback = AsyncMock()

        async def execute(self, query):
            self.commands.append(str(query))
            return FirstResult() if len(self.commands) == 1 else SecondResult()

    session = FakeSession()

    @asynccontextmanager
    async def fake_session(**_kwargs):
        yield session

    monkeypatch.setattr(policy, "get_session", fake_session)
    allowed, reason = await enforce_canonical_destination(48123, None)
    assert allowed is False
    assert reason == "explicit_connection_required_multi_account"
    assert len(session.commands) == 2
    assert "telegram_user_id" in session.commands[0]
    assert "broker_connections" in session.commands[1]
    assert "user_id" in session.commands[1]
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_database_never_implies_empty_account_portfolio(monkeypatch):
    import services.broker_routing_policy as policy

    @asynccontextmanager
    async def unavailable(**_kwargs):
        raise ConnectionError("database unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(policy, "get_session", unavailable)
    ok, reason = await enforce_canonical_destination(48123, None)
    assert not ok
    assert reason == "canonical_destination_admission_unavailable"


def test_order_route_invokes_destinations_gate_before_provider_adapters():
    source = Path("services/broker_signal_router.py").read_text(encoding="utf-8")
    assert source.index("await enforce_canonical_destination(") < source.index("await route_signal_to_bybit(")
    assert source.index("await enforce_canonical_destination(") < source.index("await route_signal_to_mt5(")
    assert "explicit_connection_required_multi_account" in Path("services/broker_routing_policy.py").read_text(encoding="utf-8")
