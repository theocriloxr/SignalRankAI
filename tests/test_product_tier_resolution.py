from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db.access import resolve_product_tier


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["owner", "admin"])
async def test_persisted_operator_tier_wins_without_subscription_query(tier: str) -> None:
    session = SimpleNamespace(execute=AsyncMock())
    user = SimpleNamespace(id=1, tier=tier, is_blocked=False, is_suspended=False)

    assert await resolve_product_tier(session, user) == tier
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("upgrade", ["premium", "vip"])
async def test_active_upgrade_sets_product_tier(upgrade: str) -> None:
    subscription = SimpleNamespace(tier=upgrade)
    session = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(subscription)))
    user = SimpleNamespace(id=2, tier="free", is_blocked=False, is_suspended=False)

    assert await resolve_product_tier(session, user) == upgrade
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_without_active_upgrade_remains_free() -> None:
    session = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(None)))
    user = SimpleNamespace(id=3, tier="premium", is_blocked=False, is_suspended=False)

    assert await resolve_product_tier(session, user) == "free"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["is_blocked", "is_suspended"])
async def test_blocked_or_suspended_user_has_no_product_access(field: str) -> None:
    values = {"id": 4, "tier": "owner", "is_blocked": False, "is_suspended": False}
    values[field] = True
    session = SimpleNamespace(execute=AsyncMock())

    assert await resolve_product_tier(session, SimpleNamespace(**values)) == "none"
    session.execute.assert_not_awaited()
